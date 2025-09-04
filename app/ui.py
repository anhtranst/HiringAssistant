import json
import os
import streamlit as st
from dotenv import load_dotenv
from pydantic import ValidationError


from graph.graph_builder import build_graph
from graph.state import AppState
from tools.analytics import log_event
from tools.exporters import checklist_json_to_docx


load_dotenv()

st.set_page_config(page_title="Hiring Assistant", layout="wide")

st.title("Hiring Assistant · Agentic HR Planner")
st.caption("LangGraph · Streamlit · Template-first + optional OpenAI refinement")

# --- Input prompt ---
default_prompt = "I need to hire a founding engineer and a GenAI intern. Can you help?"
user_prompt = st.text_area("Describe your hiring need:", value=default_prompt, height=120)

colA, colB, colC = st.columns(3)
with colA:
    timeline_weeks = st.number_input("Target timeline (weeks)", 1, 52, 6)
with colB:
    budget_usd = st.number_input("Budget (USD)", 0, 1_000_000, 8000, step=500)
with colC:
    remote_policy = st.selectbox("Location policy", ["unspecified", "remote", "hybrid", "onsite"], index=0)

st.divider()

if "last_state" not in st.session_state:
    st.session_state["last_state"] = None

if st.button("Plan Hiring", type="primary"):
    log_event("click_plan", {"timeline_weeks": timeline_weeks, "budget_usd": budget_usd})

    graph = build_graph()
    state = AppState(
        user_prompt=user_prompt.strip(),
        global_constraints={"timeline_weeks": timeline_weeks, "budget_usd": budget_usd, "location_policy": remote_policy}
    )

    # run graph
    result_state = graph.invoke(state)
    
    # LangGraph often returns a dict; coerce back to AppState for attribute access
    if isinstance(result_state, dict):
        try:
            result_state = AppState(**result_state)
        except ValidationError:
            # Fallback (shouldn't happen with our nodes), keep as dict
            pass    
    
    st.session_state["last_state"] = result_state

# --- Results ---
state = st.session_state.get("last_state")

if state is None:
    st.info("Enter your need and click **Plan Hiring** to generate JDs and a checklist.")
else:
    # Tabs for results
    t1, t2, t3, t4 = st.tabs(["🎯 Roles & JDs", "✅ Checklist / Plan", "🧰 Tools (Email/Inclusive)", "📤 Export"])

    def _get(s, name, default=None):
        if isinstance(s, dict):
            return s.get(name, default)
        return getattr(s, name, default)

    with t1:
        st.subheader("Parsed Roles")
        roles = _get(state, "roles", [])
        roles_out = [r.model_dump() if hasattr(r, "model_dump") else r for r in roles]
        st.json(roles_out)

        st.subheader("Job Descriptions")
        jds = _get(state, "jds", {})
        jds_out = {k: (v.model_dump() if hasattr(v, "model_dump") else v) for k, v in jds.items()}
        for title, jd in jds_out.items():
            st.markdown(f"### {title}")
            st.json(jd)

    with t2:
        st.subheader("Checklist (Markdown)")
        st.code(_get(state, "checklist_markdown", "") or "", language="markdown")

        st.subheader("Checklist (JSON)")
        st.json(_get(state, "checklist_json", {}) or {})

    with t3:
        st.subheader("Inclusive Language Warnings")
        st.json(_get(state, "inclusive_warnings", []) or [])
        st.subheader("Example Outreach Emails")
        st.json(_get(state, "emails", {}) or {})

    with t4:
        # Safe access (works for AppState or dict)
        def _get(s, name, default=None):
            if isinstance(s, dict):
                return s.get(name, default)
            return getattr(s, name, default)

        checklist_md = _get(state, "checklist_markdown", "") or ""
        checklist_js = _get(state, "checklist_json", {}) or {}

        # Save to disk (optional but nice for repo demo)
        os.makedirs("exports", exist_ok=True)
        md_path = os.path.join("exports", "plan.md")
        json_path = os.path.join("exports", "plan.json")

        if checklist_md:
            with open(md_path, "w", encoding="utf-8") as f:
                f.write(checklist_md)
        if checklist_js:
            with open(json_path, "w", encoding="utf-8") as f:
                json.dump(checklist_js, f, indent=2)

        st.write("Files generated in `exports/` (also downloadable here):")

        # Direct downloads (no need to reopen files)
        if checklist_md:
            st.download_button(
                "Download plan.md",
                data=checklist_md,
                file_name="plan.md",
                mime="text/markdown"
            )
        if checklist_js:
            st.download_button(
                "Download plan.json",
                data=json.dumps(checklist_js, indent=2),
                file_name="plan.json",
                mime="application/json"
            )
        # DOCX download
        if checklist_js:
            docx_bytes = checklist_json_to_docx(checklist_js)
            st.download_button(
                "Download plan.docx",
                data=docx_bytes,
                file_name="plan.docx",
                mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document"
            )
            
