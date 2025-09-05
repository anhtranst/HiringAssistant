# app/ui.py
import os
import json
import streamlit as st
from dotenv import load_dotenv
from pydantic import ValidationError

# Graph + types
from graph.graph_builder import build_graph
from graph.state import AppState

# Analytics / exports
from tools.analytics import log_event
from tools.exporters import checklist_json_to_docx

# Role creation / KB / templates / AI suggester
from tools.role_matcher import save_custom_role, load_kb
from tools.search_stub import load_template_for_role
from tools.skill_suggester import suggest_skills_with_meta  # may also return 'responsibilities'

load_dotenv()

# -----------------------
# Streamlit page config
# -----------------------
st.set_page_config(page_title="Hiring Assistant", layout="wide")
st.title("Hiring Assistant · Agentic HR Planner")
st.caption("LangGraph · Streamlit · Template-first + optional OpenAI refinement")

# -----------------------
# Small helpers
# -----------------------
def field(obj, name, default=None):
    """
    Safe attribute/field getter that works for Pydantic models and dicts.
    Avoids using dict.get on Pydantic objects.
    """
    if hasattr(obj, name):
        return getattr(obj, name)
    if isinstance(obj, dict):
        return obj.get(name, default)
    return default

def set_field(obj, name, value):
    """
    Safe setter that works for Pydantic models and dicts.
    """
    if hasattr(obj, name):
        setattr(obj, name, value)
    elif isinstance(obj, dict):
        obj[name] = value

def bump_llm_usage(state, meta: dict, feature: str):
    """
    Increment LLM usage counters if meta['used'] is True.
    Attach a minimal log entry so usage is visible in the Tools tab.
    """
    if not meta or not meta.get("used"):
        return state
    gc = _get(state, "global_constraints", {}) or {}
    gc["llm_calls"] = int(gc.get("llm_calls", 0)) + 1
    log = list(gc.get("llm_log", []))
    log.append({
        "feature": feature,          # e.g., "skill_suggestion"
        "model": meta.get("model"),
        "error": meta.get("error"),
    })
    gc["llm_log"] = log
    # Write back
    if isinstance(state, dict):
        state["global_constraints"] = gc
    else:
        state.global_constraints = gc
    return state

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
    """Safe accessor for AppState-or-dict."""
    if isinstance(s, dict):
        return s.get(name, default)
    return getattr(s, name, default)

def _invoke_and_store(state):
    """
    Run the graph, coerce dict→AppState if needed, then save to session.
    Use this everywhere we re-run the pipeline so 'last_state' is always safe.
    """
    graph = build_graph()
    result = graph.invoke(state)
    if isinstance(result, dict):
        try:
            result = AppState(**result)
        except ValidationError:
            # keep dict if coercion fails (shouldn't happen with our nodes)
            pass
    st.session_state["last_state"] = result

if state is None:
    st.info("Enter your need and click **Plan Hiring** to generate JDs and a checklist.")
else:
    # Tabs for results
    t1, t2, t3, t4 = st.tabs(["🎯 Roles & JDs", "✅ Checklist / Plan", "🧰 Tools (Email/Inclusive)", "📤 Export"])

    # ============================================================
    # Tab 1 — Roles & JDs
    # ============================================================
    with t1:
        st.subheader("Roles")
        roles = _get(state, "roles", []) or []

        # ---- Resolve unmatched roles (suggest/unknown) ----
        unresolved = [(i, r) for i, r in enumerate(roles) if field(r, "status") in ("suggest", "unknown")]
        if unresolved:
            st.warning("Some roles need confirmation. Pick a suggestion or create a new role.")

            for idx, r in unresolved:
                title = field(r, "title", "Untitled role")
                status = field(r, "status", "unknown")
                suggestions = field(r, "suggestions", []) or []

                with st.expander(f"Resolve: {title}  ·  status={status}", expanded=True):
                    # A) choose from suggestions (if any)
                    if suggestions:
                        options = {f"{s['title']} (score {s['score']:.2f})": s for s in suggestions}
                        choice_label = st.radio(
                            "Choose a suggested role template:",
                            list(options.keys()),
                            index=0,
                            key=f"suggest_choice_{idx}"
                        )
                    else:
                        options, choice_label = {}, None
                        st.info("No suggestions found for this phrase.")

                    # B) or create a new role
                    st.markdown("**Or create a new role**")
                    with st.form(f"create_role_form_{idx}", clear_on_submit=False):
                        new_title = st.text_input("Title", value=title, key=f"crt_title_{idx}")
                        function = st.selectbox("Function", ["Engineering", "Data", "Design", "GTM", "Operations"], index=0, key=f"crt_fn_{idx}")
                        seniority = st.selectbox("Seniority", ["Intern","Junior","Mid","Senior","Staff","Principal","Lead"], index=3, key=f"crt_sen_{idx}")

                        # --- Textareas controlled via session_state keys (seed once) ---
                        must_key = f"crt_must_{idx}"
                        nice_key = f"crt_nice_{idx}"
                        resp_key = f"crt_resp_{idx}"
                        if must_key not in st.session_state:
                            st.session_state[must_key] = ""
                        if nice_key not in st.session_state:
                            st.session_state[nice_key] = ""
                        if resp_key not in st.session_state:
                            st.session_state[resp_key] = ""

                        # --- Form buttons (form_submit_button inside form) ---
                        c_gen, c_submit = st.columns([1, 1])

                        with c_gen:
                            gc = _get(state, "global_constraints", {}) or {}
                            cap = int(gc.get("llm_cap", 0))
                            used = int(gc.get("llm_calls", 0))
                            ai_disabled = used >= cap

                            do_suggest = st.form_submit_button("✨ Suggest with AI", disabled=ai_disabled)
                            if do_suggest:
                                title_in = st.session_state[f"crt_title_{idx}"]
                                sen_in = st.session_state[f"crt_sen_{idx}"]
                                skills, meta = suggest_skills_with_meta(title_in, sen_in)

                                # populate skills
                                st.session_state[must_key] = ", ".join(skills.get("must", []))
                                st.session_state[nice_key] = ", ".join(skills.get("nice", []))
                                # populate responsibilities (if provided)
                                if "responsibilities" in skills:
                                    st.session_state[resp_key] = "\n".join(skills["responsibilities"])

                                last = st.session_state.get("last_state")
                                if last is not None:
                                    st.session_state["last_state"] = bump_llm_usage(last, meta, feature="skill_suggestion")
                                st.rerun()

                        with c_submit:
                            submit_new = st.form_submit_button("Create new role")

                        # Render textareas AFTER potential AI update, without value=
                        must = st.text_area("Must-have skills (comma-separated)", key=must_key)
                        nice = st.text_area("Nice-to-have skills (comma-separated)", key=nice_key)
                        resp = st.text_area("Responsibilities (one per line)", key=resp_key)

                    # Actions below the form (outside form scope)
                    c1, c2 = st.columns(2)
                    with c1:
                        if suggestions and st.button("Use selected suggestion", key=f"use_suggest_{idx}"):
                            chosen = options[choice_label]
                            # Patch RoleSpec in place
                            set_field(r, "role_id", chosen["role_id"])
                            set_field(r, "title", chosen["title"])
                            set_field(r, "status", "match")
                            set_field(r, "confidence", float(chosen["score"]))
                            kb = load_kb()
                            rec = next((k for k in kb if k["id"] == chosen["role_id"]), None)
                            set_field(r, "file", rec["file"] if rec else None)
                            set_field(r, "suggestions", [])
                            # re-run the pipeline and store safely
                            _invoke_and_store(state)
                            st.rerun()

                    with c2:
                        if submit_new:
                            loop_default = ["Screen", "Tech Deep-Dive", "System Design", "Founder Chat", "References"]
                            payload = {
                                "title": new_title.strip(),
                                "function": function,
                                "seniority": seniority,
                                "aliases": [],
                                "skills": {
                                    "must": [s.strip() for s in must.split(",") if s.strip()],
                                    "nice": [s.strip() for s in nice.split(",") if s.strip()],
                                },
                                "responsibilities": [ln.strip() for ln in resp.splitlines() if ln.strip()],
                                "interview_loop": loop_default,
                                "sourcing_tags": []
                            }
                            saved = save_custom_role(payload)
                            _ = load_kb()  # warm cache for later runs
                            set_field(r, "role_id", saved["id"])
                            set_field(r, "title", saved["title"])
                            set_field(r, "file", saved["file"])
                            set_field(r, "status", "match")
                            set_field(r, "confidence", 1.0)
                            set_field(r, "suggestions", [])
                            _invoke_and_store(state)
                            st.success(f"Created and applied custom role: {saved['title']}")
                            st.rerun()

            # Block downstream sections until all roles are finalized
            st.info("Once you confirm all roles, the Job Descriptions, Plan, and Outreach Emails will be generated.")
            st.stop()

        # ---- Matched roles: editable details + AI suggestion ----
        matched_roles = [r for r in roles if field(r, "status") == "match"]
        if not matched_roles:
            st.info("No finalized roles yet.")
        else:
            for i, r in enumerate(matched_roles):
                title = field(r, "title", "Untitled role")
                conf = field(r, "confidence", 1.0)
                st.markdown(f"### {title}  ·  ✅ Matched  · score {conf:.2f}")

                tpl = load_template_for_role(r)
                must_tpl = field(r, "must_haves") or tpl.get("must_haves") or tpl.get("skills", {}).get("must", [])
                nice_tpl = field(r, "nice_to_haves") or tpl.get("nice_to_haves") or tpl.get("skills", {}).get("nice", [])
                resp_tpl = tpl.get("responsibilities", [])
                seniority = field(r, "seniority") or tpl.get("seniority", "Mid")

                with st.expander("Edit role details", expanded=True):
                    # Title & seniority first
                    new_title = st.text_input("Title", value=title, key=f"title_{i}")
                    new_sen = st.selectbox(
                        "Seniority",
                        ["Intern", "Junior", "Mid", "Senior", "Staff", "Principal", "Lead"],
                        index=["Intern", "Junior", "Mid", "Senior", "Staff", "Principal", "Lead"].index(seniority),
                        key=f"sen_{i}"
                    )

                    # --- Keys for textareas & initial seeding ---
                    must_key = f"must_{i}"
                    nice_key = f"nice_{i}"
                    resp_key = f"resp_{i}"
                    if must_key not in st.session_state:
                        st.session_state[must_key] = ", ".join(must_tpl)
                    if nice_key not in st.session_state:
                        st.session_state[nice_key] = ", ".join(nice_tpl)
                    if resp_key not in st.session_state:
                        st.session_state[resp_key] = "\n".join(resp_tpl)

                    # --- AI Suggestion button BEFORE textareas ---
                    gc = _get(state, "global_constraints", {}) or {}
                    cap = int(gc.get("llm_cap", 0))
                    used = int(gc.get("llm_calls", 0))
                    ai_disabled = used >= cap

                    ai_cols = st.columns([1, 3])
                    with ai_cols[0]:
                        if st.button("✨ Suggest with AI", key=f"regen_{i}", disabled=ai_disabled):
                            title_in = st.session_state.get(f"title_{i}", new_title)
                            sen_in = st.session_state.get(f"sen_{i}", new_sen)

                            skills, meta = suggest_skills_with_meta(title_in, sen_in)

                            st.session_state[must_key] = ", ".join(skills.get("must", []))
                            st.session_state[nice_key] = ", ".join(skills.get("nice", []))
                            if "responsibilities" in skills:
                                st.session_state[resp_key] = "\n".join(skills["responsibilities"])

                            last = st.session_state.get("last_state")
                            if last is not None:
                                st.session_state["last_state"] = bump_llm_usage(last, meta, feature="skill_suggestion")
                            st.rerun()
                    with ai_cols[1]:
                        if cap:
                            st.caption(f"LLM calls: {used}/{cap}")

                    # Text areas (no value= when using keys)
                    must_s = st.text_area("Must-have skills (comma-separated)", key=must_key)
                    nice_s = st.text_area("Nice-to-have skills (comma-separated)", key=nice_key)
                    resp_s = st.text_area("Responsibilities (one per line)", key=resp_key)

                    colx, coly = st.columns(2)
                    with colx:
                        if st.button("Apply changes for this plan", key=f"apply_{i}"):
                            set_field(r, "title", (st.session_state.get(f"title_{i}") or new_title).strip() or title)
                            set_field(r, "seniority", st.session_state.get(f"sen_{i}", new_sen))
                            set_field(r, "must_haves", [s.strip() for s in must_s.split(",") if s.strip()])
                            set_field(r, "nice_to_haves", [s.strip() for s in nice_s.split(",") if s.strip()])
                            set_field(r, "responsibilities", [ln.strip() for ln in resp_s.splitlines() if ln.strip()])

                            _invoke_and_store(state)
                            st.success("Changes applied for this run.")
                            st.rerun()

                    with coly:
                        save_it = st.checkbox("Also save as a reusable custom template", key=f"save_{i}", value=False)
                        if save_it and st.button("Save as custom template", key=f"savebtn_{i}"):
                            payload = {
                                "title": (st.session_state.get(f"title_{i}") or new_title).strip() or title,
                                "function": "Engineering",
                                "seniority": st.session_state.get(f"sen_{i}", new_sen),
                                "aliases": [],
                                "skills": {
                                    "must": [s.strip() for s in must_s.split(",") if s.strip()],
                                    "nice": [s.strip() for s in nice_s.split(",") if s.strip()],
                                },
                                "responsibilities": [ln.strip() for ln in resp_s.splitlines() if ln.strip()],
                                "interview_loop": tpl.get("interview_loop", ["Screen","Tech Deep-Dive","System Design","Founder Chat","References"]),
                                "sourcing_tags": tpl.get("sourcing_tags", [])
                            }
                            saved = save_custom_role(payload)
                            set_field(r, "role_id", saved["id"])
                            set_field(r, "title", saved["title"])
                            set_field(r, "file", saved["file"])
                            set_field(r, "status", "match")
                            set_field(r, "confidence", 1.0)

                            _invoke_and_store(state)
                            st.success(f"Saved as custom template: {saved['title']}")
                            st.rerun()

        # ----- JDs preview -----
        st.subheader("Job Descriptions")
        jds = _get(state, "jds", {})
        jds_out = {k: (v.model_dump() if hasattr(v, "model_dump") else v) for k, v in jds.items()}
        for title, jd in jds_out.items():
            st.markdown(f"### {title}")
            st.json(jd)

    # ============================================================
    # Tab 2 — Checklist / Plan
    # ============================================================
    with t2:
        st.subheader("Checklist (Markdown)")
        st.code(_get(state, "checklist_markdown", "") or "", language="markdown")

        st.subheader("Checklist (JSON)")
        st.json(_get(state, "checklist_json", {}) or {})

    # ============================================================
    # Tab 3 — Tools
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
    # Tab 4 — Export
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
