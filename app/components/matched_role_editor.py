# app/components/matched_role_editor.py
import streamlit as st

# Helpers (safe getters/setters + LLM usage bump)
from services.state_helpers import field, set_field, _get, bump_llm_usage

# Template loading + AI skill suggester
from tools.search_stub import load_template_for_role
from tools.skill_suggester import suggest_skills_with_meta

# >>> NEW: actually persist custom templates when user clicks "Save as custom template"
from tools.role_matcher import save_custom_role


def matched_role_editor(i, role, state, invoke_and_store_cb):
    """
    Renders an editor for one matched role:
      - Edits title/seniority/skills/responsibilities
      - "Suggest with AI" (respects LLM cap)
      - Apply changes (re-runs graph for this run only)
      - Save as reusable custom template (PERSISTS to data/role_knowledge_custom/)
    """
    title = field(role, "title", "Untitled role")
    conf = field(role, "confidence", 1.0)
    st.markdown(f"### {title}  ·  ✅ Matched  · score {conf:.2f}")

    tpl = load_template_for_role(role)
    must_tpl = field(role, "must_haves") or tpl.get("skills", {}).get("must", [])   # role overrides, else template
    nice_tpl = field(role, "nice_to_haves") or tpl.get("skills", {}).get("nice", [])
    resp_tpl = tpl.get("responsibilities", [])
    seniority = field(role, "seniority") or tpl.get("seniority", "Mid")

    changed = False
    with st.expander("Edit role details", expanded=True):
        # ----- Header fields -----
        new_title = st.text_input("Title", value=title, key=f"title_{i}")
        new_sen = st.selectbox(
            "Seniority",
            ["Intern", "Junior", "Mid", "Senior", "Staff", "Principal", "Lead"],
            index=["Intern", "Junior", "Mid", "Senior", "Staff", "Principal", "Lead"].index(seniority),
            key=f"sen_{i}"
        )

        # ----- Seed textareas via session_state keys (once) -----
        must_key, nice_key, resp_key = f"must_{i}", f"nice_{i}", f"resp_{i}"
        ss = st.session_state
        ss.setdefault(must_key, ", ".join(must_tpl))
        ss.setdefault(nice_key, ", ".join(nice_tpl))
        ss.setdefault(resp_key, "\n".join(resp_tpl))

        # ----- AI Suggestion (respects cap) -----
        gc = _get(state, "global_constraints", {}) or {}
        cap, used = int(gc.get("llm_cap", 0)), int(gc.get("llm_calls", 0))
        ai_disabled = used >= cap

        a, b = st.columns([1, 3])
        with a:
            if st.button("✨ Suggest with AI", key=f"regen_{i}", disabled=ai_disabled):
                title_in = ss.get(f"title_{i}", new_title)
                sen_in = ss.get(f"sen_{i}", new_sen)
                skills, meta = suggest_skills_with_meta(title_in, sen_in)

                ss[must_key] = ", ".join(skills.get("must", []))
                ss[nice_key] = ", ".join(skills.get("nice", []))
                if "responsibilities" in skills:
                    ss[resp_key] = "\n".join(skills["responsibilities"])

                last = st.session_state.get("last_state")
                if last is not None:
                    st.session_state["last_state"] = bump_llm_usage(last, meta, feature="skill_suggestion")
                st.rerun()
        with b:
            if cap:
                st.caption(f"LLM calls: {used}/{cap}")

        # ----- Textareas (bound to keys) -----
        must_s = st.text_area("Must-have skills (comma-separated)", key=must_key)
        nice_s = st.text_area("Nice-to-have skills (comma-separated)", key=nice_key)
        resp_s = st.text_area("Responsibilities (one per line)", key=resp_key)

        colx, coly = st.columns(2)

        # ----- Apply (this run only) -----
        with colx:
            if st.button("Apply changes for this plan", key=f"apply_{i}"):
                set_field(role, "title", (ss.get(f"title_{i}") or new_title).strip() or title)
                set_field(role, "seniority", ss.get(f"sen_{i}", new_sen))
                set_field(role, "must_haves", [s.strip() for s in must_s.split(",") if s.strip()])
                set_field(role, "nice_to_haves", [s.strip() for s in nice_s.split(",") if s.strip()])
                set_field(role, "responsibilities", [ln.strip() for ln in resp_s.splitlines() if ln.strip()])
                invoke_and_store_cb(state)
                st.success("Changes applied for this run.")
                changed = True
                st.rerun()

        # ----- Save as reusable custom template (PERSIST) -----
        with coly:
            save_it = st.checkbox("Also save as a reusable custom template", key=f"save_{i}", value=False)
            if save_it and st.button("Save as custom template", key=f"savebtn_{i}"):
                payload = {
                    "title": (ss.get(f"title_{i}") or new_title).strip() or title,
                    "function": "Engineering",
                    "seniority": ss.get(f"sen_{i}", new_sen),
                    "aliases": [],
                    "skills": {
                        "must": [s.strip() for s in must_s.split(",") if s.strip()],
                        "nice": [s.strip() for s in nice_s.split(",") if s.strip()],
                    },
                    "responsibilities": [ln.strip() for ln in resp_s.splitlines() if ln.strip()],
                    "interview_loop": tpl.get("interview_loop", ["Screen","Tech Deep-Dive","System Design","Founder Chat","References"]),
                    "sourcing_tags": tpl.get("sourcing_tags", []),
                }

                # >>> persist to data/role_knowledge_custom/ + update roles_kb_custom.json
                saved = save_custom_role(payload)

                # Patch current in-memory RoleSpec so the session immediately uses the new template
                set_field(role, "role_id", saved["id"])
                set_field(role, "title", saved["title"])
                set_field(role, "file", saved["file"])   # e.g. "data/role_knowledge_custom/<slug>.json"
                set_field(role, "status", "match")
                set_field(role, "confidence", 1.0)

                # Re-run the graph so downstream JDs/plan pick up new template
                invoke_and_store_cb(state)
                st.success(f"Saved as custom template: {saved['title']}")
                changed = True
                st.rerun()

    return changed
