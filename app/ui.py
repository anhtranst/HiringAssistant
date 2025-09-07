# app/ui.py
import os
import json
import streamlit as st
from dotenv import load_dotenv
from pydantic import ValidationError

# Graph + types (used for the initial "Plan Hiring" run)
from graph.graph_builder import build_graph
from graph.state import AppState

# Analytics / exports (Tabs 2–4 keep using these)
from tools.analytics import log_event
from tools.exporters import checklist_json_to_docx

# Tab 1 is delegated to its own module
from tabs.roles_tab import render_roles_tab

load_dotenv()

# -----------------------
# Streamlit page config
# -----------------------
st.set_page_config(page_title="Hiring Assistant", layout="wide")
st.title("Hiring Assistant · Agentic HR Planner")
st.caption("LangGraph · Streamlit · Template-first + optional OpenAI refinement")

# -----------------------
# Input controls
# -----------------------
default_prompt = "I need to hire a founding engineer and a GenAI intern. Can you help?"
user_prompt = st.text_area("Describe your hiring need:", value=default_prompt, height=120)

colA, colB, colC = st.columns(3)
with colA:
    timeline_weeks = st.number_input("Target timeline (weeks)", 1, 52, 6)
with colB:
    budget_usd = st.number_input("Budget (USD)", 0, 1_000_000, 8000, step=500)
with colC:
    remote_policy = st.selectbox("Location policy", ["unspecified", "remote", "hybrid", "onsite"], index=0)

# LLM controls
use_llm = st.toggle("Use LLM to polish JD text (optional)", value=False)
llm_cap = st.number_input("Max LLM calls for this run", min_value=1, max_value=50, value=5, step=1)
st.caption(f"LLM refinement: {'ON' if use_llm and os.getenv('OPENAI_API_KEY') else 'OFF'}")

st.divider()

# Keep last run's state
if "last_state" not in st.session_state:
    st.session_state["last_state"] = None

# -----------------------
# Run the graph (initial)
# -----------------------
if st.button("Plan Hiring", type="primary"):
    log_event("click_plan", {"timeline_weeks": timeline_weeks, "budget_usd": budget_usd})

    graph = build_graph()
    state = AppState(
        user_prompt=user_prompt.strip(),
        global_constraints={
            "timeline_weeks": int(timeline_weeks),
            "budget_usd": int(budget_usd),
            "location_policy": remote_policy,
            "use_llm": bool(use_llm),
            "llm_cap": int(llm_cap),
            "llm_calls": 0,   # start-of-run counter
        },
    )

    # Run the graph
    result_state = graph.invoke(state)

    # LangGraph can return dicts; coerce to AppState if needed
    if isinstance(result_state, dict):
        try:
            result_state = AppState(**result_state)
        except ValidationError:
            pass

    st.session_state["last_state"] = result_state

# -----------------------
# Results rendering
# -----------------------
state = st.session_state.get("last_state")

def _get(s, name, default=None):
    """Safe accessor for AppState-or-dict (used by Tabs 2–4)."""
    if isinstance(s, dict):
        return s.get(name, default)
    return getattr(s, name, default)

if state is None:
    st.info("Enter your need and click **Plan Hiring** to generate JDs and a checklist.")
else:
    # Tabs for results
    t1, t2, t3, t4 = st.tabs(["🎯 Roles & JDs", "✅ Checklist / Plan", "🧰 Tools (Email/Inclusive)", "📤 Export"])

    # ============================================================
    # Tab 1 — Roles & JDs (delegated)
    # ============================================================
    with t1:
        render_roles_tab(state)

    # ============================================================
    # Tab 2 — Checklist / Plan (unchanged)
    # ============================================================
    with t2:
        st.subheader("Checklist (Markdown)")
        st.code(_get(state, "checklist_markdown", "") or "", language="markdown")

        st.subheader("Checklist (JSON)")
        st.json(_get(state, "checklist_json", {}) or {})

    # ============================================================
    # Tab 3 — Tools (unchanged)
    # ============================================================
    with t3:
        st.subheader("Inclusive Language Warnings")
        st.json(_get(state, "inclusive_warnings", []) or [])

        st.subheader("Example Outreach Emails")
        st.json(_get(state, "emails", {}) or {})

        st.subheader("LLM usage (this run)")
        gc = _get(state, "global_constraints", {}) or {}
        st.json({
            "toggle": gc.get("use_llm"),
            "key_loaded": bool(os.getenv("OPENAI_API_KEY")),
            "calls_used": gc.get("llm_calls", 0),
            "cap": gc.get("llm_cap", 0),
            "log": gc.get("llm_log", []),
        })

    # ============================================================
    # Tab 4 — Export (unchanged)
    # ============================================================
    with t4:
        checklist_md = _get(state, "checklist_markdown", "") or ""
        checklist_js = _get(state, "checklist_json", {}) or {}

        # Save to disk for demo (optional)
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

        # Direct downloads
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
