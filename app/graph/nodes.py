# app/graph/nodes.py
import os
import json
from typing import List, Dict, Tuple

from graph.state import AppState, RoleSpec, JD

# Deterministic matcher + KB
from tools.role_matcher import load_kb, extract_candidate_phrases, match_one

# Optional LLM intake extractor (whole-prompt → list of roles)
from tools.llm_extractor import extract_roles_with_llm

# Unified template loader (curated or custom) by RoleSpec.file
from tools.search_stub import load_template_for_role

# Downstream utilities
from tools.checklist import build_checklist
from tools.email_writer import outreach_templates
from tools.inclusive_check import check_inclusive_language
from tools.simulator import quick_success_estimate

# LLM usage counter (so Tools tab shows accurate usage)
from services.state_helpers import bump_llm_usage


# NOTE: We intentionally avoid caching KB at import time so that newly-saved
# custom roles are immediately discoverable on the next run.
# If you want an in-memory cache, you can add one with a short TTL.
# KB = load_kb()


# --- Node 1: intake / parse prompt into RoleSpecs ---------------------------
def node_intake(state: AppState) -> AppState:
    """
    Parse the user's free-text prompt into one or more RoleSpec entries.

    Strategy:
      1) If roles already exist (set by the UI resolver), skip parsing.
      2) Otherwise, extract intended roles from the full prompt:
         - If `use_llm` is true AND we still have LLM budget, call the LLM
           to extract role titles (e.g., "Full Stack Engineer", "GenAI Intern").
         - If LLM is off/unavailable/failed, fall back to the heuristic extractor.
      3) For each extracted title, call `match_one` to get top-3 suggestions
         (status="suggest"), and store them on RoleSpec.suggestions.
      4) As a safety net, if absolutely nothing resolved, add a curated
         "Founding Engineer" so downstream nodes don't break.
    """
    # --- 0) Early exit: the UI already resolved roles
    if state.roles:
        return state

    prompt = state.user_prompt or ""

    # --- 1) Decide whether we can/should use the LLM for extraction
    gc = state.global_constraints or {}
    use_llm_flag = bool(gc.get("use_llm"))
    cap = int(gc.get("llm_cap", 0))
    used = int(gc.get("llm_calls", 0))
    remaining = max(0, cap - used)
    have_key = bool(os.getenv("OPENAI_API_KEY"))

    titles: List[str] = []

    # --- 2) LLM-first extraction path (respects cap + env key)
    if use_llm_flag and have_key and remaining > 0:
        roles_llm, meta = extract_roles_with_llm(prompt)
        # meta.used=True if the call actually hit the LLM
        state = bump_llm_usage(state, meta, feature="intake_extraction")
        titles = [r["title"] for r in roles_llm if r.get("title")]

    # --- 3) Heuristic fallback (or if LLM returned nothing)
    if not titles:
        titles = extract_candidate_phrases(prompt, use_llm=False)

    # --- 4) Match each extracted title to KB (top-3 suggestions)
    kb = load_kb()  # fresh KB each run so new customs appear immediately
    results: List[RoleSpec] = []

    for title in titles:
        m = match_one(title, kb, fuzzy_threshold=88)
        # match_one() returns status="suggest" + top-3 suggestions by design.
        # We still carry through file/id if they exist (e.g., exact hit).
        results.append(RoleSpec(
            role_id=m.role_id,
            title=m.title,
            status=m.status,             # "suggest" or "unknown"
            confidence=m.confidence,
            file=m.file,
            suggestions=m.suggestions    # [{role_id, title, score, is_custom, created_at}]
        ))

    # --- 5) Safety net: if nothing is matched at all, add Founding Engineer
    if not results or all(r.status != "match" and not r.suggestions for r in results):
        fallback = next((k for k in kb if k["id"] == "founding_engineer"), None)
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


# --- Node 2: role profiler (enrich-only; never clobber user edits) ----------
def node_profile(state: AppState) -> AppState:
    """
    For each role, load its template and FILL ONLY MISSING FIELDS.
    We never overwrite fields already edited by the user or previously set.

    Notes on template schema:
      - Curated CORE files may still carry legacy keys (must_haves/nice_to_haves).
      - Custom and newer CORE files use the canonical shape: skills.{must,nice}.
      - We support both by checking skills first, then legacy keys.
    """
    for idx, role in enumerate(state.roles):
        tpl = load_template_for_role(role) or {}

        # Read canonical skills first, then fall back to legacy keys if present.
        tpl_must = (tpl.get("skills", {}).get("must") or tpl.get("must_haves") or [])
        tpl_nice = (tpl.get("skills", {}).get("nice") or tpl.get("nice_to_haves") or [])
        tpl_resp = tpl.get("responsibilities", []) or []

        # Fill only if missing on RoleSpec (don't clobber UI edits)
        if not role.must_haves:
            role.must_haves = list(tpl_must)

        if not role.nice_to_haves:
            role.nice_to_haves = list(tpl_nice)

        if not role.responsibilities:
            role.responsibilities = list(tpl_resp)

        if not role.seniority:
            role.seniority = tpl.get("seniority", role.seniority or "Mid")

        # Prefer existing role.geo; otherwise, take from global constraints if present
        role.geo = role.geo or state.global_constraints.get("geo")

        state.roles[idx] = role

    return state


# --- LLM helper for JD refinement (optional polish) -------------------------
def refine_text_via_llm(jd_dict: Dict, use_llm: bool, remaining_calls: int) -> Tuple[Dict, int, Dict]:
    """
    Returns a 3-tuple: (refined_dict, remaining_calls, meta)
    meta includes: used, model, prompt_tokens, completion_tokens, total_tokens, error, reason

    No-op when:
      - LLM disabled
      - No API key
      - No remaining calls in the cap
    """
    # No-op path
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


# --- Node 3: JD compose (template-first; optional LLM refine) ----------------
def node_jd(state: AppState) -> AppState:
    """
    Build JD objects per role using the template facts. Optionally run a cheap
    LLM pass to polish the text (strict JSON in/out). Respects `llm_cap`.
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
        state.global_constraints["llm_calls"] = cap - remaining  # keep invariant
        state.global_constraints["llm_log"] = llm_log
        return state

    for role in matched_roles:
        tpl = load_template_for_role(role)

        # Canonical-first, legacy fallback for requirements
        must = role.must_haves or tpl.get("skills", {}).get("must", []) or tpl.get("must_haves", [])
        nice = role.nice_to_haves or tpl.get("skills", {}).get("nice", []) or tpl.get("nice_to_haves", [])

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

    # Update LLM accounting (total used so far in this run)
    state.global_constraints["llm_calls"] = cap - remaining
    state.global_constraints["llm_log"] = llm_log
    return state


# --- Node 4: Checklist / plan + helpers -------------------------------------
def node_plan(state: AppState) -> AppState:
    """
    Produce the hiring checklist/plan artifacts and utility outputs for the UI.
    Only runs when there are finalized roles and built JDs.
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
