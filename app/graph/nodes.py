import os
import json
from typing import List, Dict
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
def refine_text_via_llm(jd_dict: Dict) -> Dict:
    # Optional: only run if API key is present
    if not os.getenv("OPENAI_API_KEY"):
        return jd_dict

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
            response_format={ "type": "json_object" }
        )
        content = response.choices[0].message.content
        return json.loads(content)
    except Exception:
        # fail safe: keep original
        return jd_dict

def node_jd(state: AppState) -> AppState:
    for role in state.roles:
        facts = role_knowledge(role.title)

        jd = JD(
            title=role.title,
            mission=facts.get("mission", f"Contribute to building our v1 product as a {role.title}."),
            responsibilities=facts.get("responsibilities", []),
            requirements=role.must_haves or facts.get("must_haves", []),
            nice_to_haves=role.nice_to_haves or facts.get("nice_to_haves", []),
            benefits=["Equity", "Flexible work", "Growth opportunities"]
        )

        refined = refine_text_via_llm(jd.model_dump())
        state.jds[role.title] = JD(**refined)
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
