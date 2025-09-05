import os
import json
from typing import List, Dict, Tuple
from graph.state import AppState, RoleSpec, JD
from tools.search_stub import role_knowledge
from tools.checklist import build_checklist
from tools.email_writer import outreach_templates
from tools.inclusive_check import check_inclusive_language
from tools.simulator import quick_success_estimate

# --- Node 1: intake / simple parse ---
def node_intake(state: AppState) -> AppState:
    # Very simple split by common delimiters; robust parsing could be added later
    prompt = state.user_prompt.lower()
    titles: List[str] = []

    candidates = ["founding engineer", "genai intern", "backend engineer", "data scientist", "frontend engineer"]
    for t in candidates:
        if t in prompt:
            titles.append(t)

    # Fallback: if none recognized, assume one generic role "founding engineer"
    if not titles:
        titles = ["founding engineer"]

    state.roles = [RoleSpec(title=title.title()) for title in titles]
    return state

# --- Node 2: role profiler ---
def node_profile(state: AppState) -> AppState:
    for idx, role in enumerate(state.roles):
        facts = role_knowledge(role.title)
        role.must_haves = facts.get("must_haves", [])
        role.nice_to_haves = facts.get("nice_to_haves", [])
        role.seniority = facts.get("seniority", role.seniority)
        role.geo = role.geo or state.global_constraints.get("geo")
        state.roles[idx] = role
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
    use_llm = bool(state.global_constraints.get("use_llm"))
    cap = int(state.global_constraints.get("llm_cap", 0))
    used = int(state.global_constraints.get("llm_calls", 0))
    remaining = max(0, cap - used)
    llm_log = []

    for role in state.roles:
        facts = role_knowledge(role.title)
        jd = JD(
            title=role.title,
            mission=facts.get("mission", f"Contribute to building our v1 product as a {role.title}."),
            responsibilities=facts.get("responsibilities", []),
            requirements=role.must_haves or facts.get("must_haves", []),
            nice_to_haves=role.nice_to_haves or facts.get("nice_to_haves", []),
            benefits=["Equity", "Flexible work", "Growth opportunities"],
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
    md, js = build_checklist(state.roles, state.jds, state.global_constraints)
    state.checklist_markdown = md
    state.checklist_json = js

    # Extra utilities for the UI
    state.emails = outreach_templates(list(state.jds.keys()))
    state.inclusive_warnings = check_inclusive_language("\n".join(
        [" ".join(jd.requirements + jd.responsibilities) for jd in state.jds.values()]
    ))

    # quick probability estimate for fun (not shown yet in UI tabs)
    _ = quick_success_estimate(js)
    return state
