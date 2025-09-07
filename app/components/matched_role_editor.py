# app/components/matched_role_editor.py
import streamlit as st

# Helpers (safe getters/setters + LLM usage bump)
from services.state_helpers import field, set_field, _get, bump_llm_usage

# Template loading + AI skill suggester
from tools.search_stub import load_template_for_role
from tools.skill_suggester import suggest_skills_with_meta

# >>> Persist custom templates when user clicks "Save as custom template"
from tools.role_matcher import save_custom_role


def matched_role_editor(i, role, state, invoke_and_store_cb):
    """
    Renders an editor for one matched role.

    IMPORTANT: This component now uses the passed-in callback for persistence ONLY.
    The parent (roles_tab) supplies a *store-only* wrapper so that edits do not
    trigger a heavy recompute. HR will click a single "Generate plan & JDs" button
    later to rebuild everything at once.
    """
    title = field(role, "title", "Untitled role")
    conf = field(role, "confidence", None)
    conf_src = field(role, "confidence_source")

    # Header: show "Selected by HR" if manual; else show numeric score
    if conf_src == "manual" or conf is None:
        st.markdown(f"### {title}  ·  ✅ Matched  · Selected by HR")
    else:
        try:
            st.markdown(f"### {title}  ·  ✅ Matched  · score {float(conf):.2f}")
        except Exception:
            st.markdown(f"### {title}  ·  ✅ Matched")

    tpl = load_template_for_role(role)
    must_tpl = field(role, "must_haves") or tpl.get("skills", {}).get("must", [])
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

                # Context-aware: polish existing text or generate if blanks
                drafts = {
                    "must": ss.get(must_key, ""),
                    "nice": ss.get(nice_key, ""),
                    "responsibilities": ss.get(resp_key, ""),
                    # mission is handled elsewhere; JD node composes/uses it
                }
                # Function can be inferred from template or role meta; pass None if unknown
                function = tpl.get("function") or None

                skills, meta = suggest_skills_with_meta(title_in, sen_in, function, drafts)
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
            st.caption("Edits are saved without rebuilding. Use **Generate plan & JDs** to refresh outputs.")

        # ----- Textareas (bound to keys) -----
        must_s = st.text_area("Must-have skills (comma-separated)", key=must_key)
        nice_s = st.text_area("Nice-to-have skills (comma-separated)", key=nice_key)
        resp_s = st.text_area("Responsibilities (one per line)", key=resp_key)

        colx, coly = st.columns(2)

        # ----- Save (store-only) -----
        with colx:
            if st.button("Save changes (no rebuild)", key=f"apply_{i}"):
                set_field(role, "title", (ss.get(f"title_{i}") or new_title).strip() or title)
                set_field(role, "seniority", ss.get(f"sen_{i}", new_sen))
                set_field(role, "must_haves", [s.strip() for s in must_s.split(",") if s.strip()])
                set_field(role, "nice_to_haves", [s.strip() for s in nice_s.split(",") if s.strip()])
                set_field(role, "responsibilities", [ln.strip() for ln in resp_s.splitlines() if ln.strip()])

                # Persist to session only; mark plan as stale via the provided callback
                invoke_and_store_cb(state)
                st.success("Saved. Click **Generate plan & JDs** to rebuild outputs.")
                changed = True
                st.rerun()

        # ----- Save as reusable custom template (store-only) -----
        with coly:
            save_it = st.checkbox("Also save as a reusable custom template", key=f"save_{i}", value=False)
            if save_it and st.button("Save as custom template (no rebuild)", key=f"savebtn_{i}"):
                payload = {
                    "title": (ss.get(f"title_{i}") or new_title).strip() or title,
                    "function": tpl.get("function", "Engineering"),
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

                saved = save_custom_role(payload)

                # Patch current in-memory RoleSpec so the session immediately uses the new template
                set_field(role, "role_id", saved["id"])
                set_field(role, "title", saved["title"])
                set_field(role, "file", saved["file"])
                set_field(role, "status", "match")
                set_field(role, "confidence", None)
                set_field(role, "confidence_source", "manual")

                # Store-only; mark as stale via callback
                invoke_and_store_cb(state)
                st.success(f"Saved as custom template: {saved['title']}. Click **Generate plan & JDs** to rebuild.")
                changed = True
                st.rerun()

    return changed
