import os
import json
from typing import List, Dict, Tuple
from graph.state import AppState, RoleSpec, JD

# Matcher + KB helpers (deterministic; no LLM)
from tools.role_matcher import load_kb, extract_candidate_phrases, match_one

# Template loader now works by file path provided on RoleSpec.file
from tools.search_stub import load_template_for_role

# Downstream utilities
from tools.checklist import build_checklist
from tools.email_writer import outreach_templates
from tools.inclusive_check import check_inclusive_language
from tools.simulator import quick_success_estimate

# Load KB once at import; if you support adding roles at runtime,
# you can refresh this by calling load_kb() again after saving a role.
KB = load_kb()


# --- Node 1: intake / simple parse ---
def node_intake(state: AppState) -> AppState:
    """
    Parse the user's free-text prompt into one or more RoleSpec entries by
    matching phrases against our role KB (titles + aliases). If the UI has
    already resolved roles (e.g., user picked a suggestion or created a
    new custom role), we skip parsing and keep those roles intact.
    """
    # --- Early exit: if roles already resolved in UI, skip parsing ---
    if state.roles:   # roles already chosen/resolved in UI
        return state

    prompt = state.user_prompt
    phrases = extract_candidate_phrases(prompt)
    results: List[RoleSpec] = []

    for ph in phrases:
        m = match_one(ph, KB, fuzzy_threshold=88)
        results.append(RoleSpec(
            role_id=m.role_id,
            title=m.title,
            status=m.status,
            confidence=m.confidence,
            file=m.file,
            suggestions=m.suggestions
        ))

    # If absolutely nothing matched, add a safe default so downstream won't crash
    if not any(r.status == "match" for r in results):
        # Try to find founding engineer in KB
        fallback = next((k for k in KB if k["id"] == "founding_engineer"), None)
        if fallback:
            results.append(RoleSpec(
                role_id=fallback["id"],
                title=fallback["title"],
                status="match",
                confidence=1.0,
                file=fallback["file"],
                suggestions=[]
            ))

    state.roles = results
    return state


# --- Node 2: role profiler ---
def node_profile(state: AppState) -> AppState:
    # Only enrich roles that are finalized (status == "match")
    for idx, role in enumerate([r for r in state.roles if r.status == "match"]):
        tpl = load_template_for_role(role)
        role.must_haves = tpl.get("must_haves", []) or tpl.get("skills", {}).get("must", [])
        role.nice_to_haves = tpl.get("nice_to_haves", []) or tpl.get("skills", {}).get("nice", [])
        role.seniority = role.seniority or tpl.get("seniority")
        role.geo = role.geo or state.global_constraints.get("geo")
    return state


# --- Node 3: JD compose (template-first; optional LLM refine) ---
def refine_text_via_llm(jd_dict: Dict, use_llm: bool, remaining_calls: int) -> Tuple[Dict, int, Dict]:
    """
    Returns a 3-tuple: (refined_dict, remaining_calls, meta)
    meta includes keys like: used, model, prompt_tokens, completion_tokens, total_tokens, error, reason
    """
    # No-op path: LLM disabled or no key or no remaining calls
    if not use_llm or not os.getenv("OPENAI_API_KEY") or remaining_calls <= 0:
        return jd_dict, remaining_calls, {"used": False, "reason": "disabled_or_no_key_or_cap"}

    try:
        from openai import OpenAI
        client = OpenAI()
        system = (
            "You are an HR writing assistant. "
            "Return ONLY valid JSON with the same keys. "
            "Keep bullets concise and inclusive. Do not invent compensation."
        )
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": json.dumps(jd_dict)}
            ],
            response_format={"type": "json_object"}
        )
        refined = json.loads(response.choices[0].message.content)
        usage = getattr(response, "usage", None)
        meta = {
            "used": True,
            "model": "gpt-4o-mini",
            "prompt_tokens": getattr(usage, "prompt_tokens", None),
            "completion_tokens": getattr(usage, "completion_tokens", None),
            "total_tokens": getattr(usage, "total_tokens", None),
        }
        return refined, remaining_calls - 1, meta
    except Exception as e:
        # Fail safe: return original dict, keep remaining_calls, include error message
        return jd_dict, remaining_calls, {"used": False, "error": str(e)}


def node_jd(state: AppState) -> AppState:
    """
    Build JD objects per role using the template facts. Optionally run a cheap
    LLM pass to polish the text (strict JSON in/out).
    """
    use_llm = bool(state.global_constraints.get("use_llm"))
    cap = int(state.global_constraints.get("llm_cap", 0))
    used = int(state.global_constraints.get("llm_calls", 0))
    remaining = max(0, cap - used)
    llm_log = []

    # Reset JDs each run to avoid leftovers from previous resolutions
    state.jds = {}

    matched_roles = [r for r in state.roles if r.status == "match"]
    if not matched_roles:
        # Nothing finalized yet → nothing to do
        state.global_constraints["llm_calls"] = cap - remaining
        state.global_constraints["llm_log"] = llm_log
        return state

    for role in matched_roles:
        tpl = load_template_for_role(role)
        must = role.must_haves or tpl.get("must_haves", []) or tpl.get("skills", {}).get("must", [])
        nice = role.nice_to_haves or tpl.get("nice_to_haves", []) or tpl.get("skills", {}).get("nice", [])

        jd = JD(
            title=role.title,
            mission=tpl.get("mission", f"Contribute to building our v1 product as a {role.title}."),
            responsibilities=tpl.get("responsibilities", []),
            requirements=must,
            nice_to_haves=nice,
            benefits=tpl.get("benefits", ["Equity", "Flexible work", "Growth opportunities"]),
        )

        refined_dict, remaining, meta = refine_text_via_llm(jd.model_dump(), use_llm, remaining)
        meta["role"] = role.title
        llm_log.append(meta)
        state.jds[role.title] = JD(**refined_dict)

    state.global_constraints["llm_calls"] = cap - remaining
    state.global_constraints["llm_log"] = llm_log
    return state


# --- Node 4: Checklist / plan + helpers ---
def node_plan(state: AppState) -> AppState:
    """
    Produce the hiring checklist/plan artifacts and utility outputs for the UI.
    """
    matched_roles = [r for r in state.roles if r.status == "match"]
    if not matched_roles or not state.jds:
        # Clear outputs until roles are finalized
        state.checklist_markdown = ""
        state.checklist_json = {}
        state.emails = {}
        state.inclusive_warnings = []
        _ = quick_success_estimate({})  # no-op
        return state

    md, js = build_checklist(matched_roles, state.jds, state.global_constraints)
    state.checklist_markdown = md
    state.checklist_json = js

    # Only generate outreach emails for finalized JD titles
    state.emails = outreach_templates(list(state.jds.keys()))

    state.inclusive_warnings = check_inclusive_language("\n".join(
        [" ".join(jd.requirements + jd.responsibilities) for jd in state.jds.values()]
    ))
    _ = quick_success_estimate(js)
    return state
