# app/components/matched_role_editor.py
import streamlit as st

# Helpers (safe getters/setters + LLM usage bump)
from services.state_helpers import field, set_field, _get, bump_llm_usage

# Template loading + AI skill suggester
from tools.search_stub import load_template_for_role
from tools.skill_suggester import suggest_skills_with_meta

# >>> NEW: actually persist custom templates when user clicks "Save as custom template"
from tools.role_matcher import save_custom_role

def _to_csv(val) -> str:
    """Return a comma-separated string from list or pass through string."""
    if isinstance(val, list):
        return ", ".join([str(x).strip() for x in val if str(x).strip()])
    if isinstance(val, str):
        return val.strip()
    return ""

def _to_lines(val) -> str:
    """Return a newline-separated string from list or pass through string."""
    if isinstance(val, list):
        return "\n".join([str(x).strip() for x in val if str(x).strip()])
    if isinstance(val, str):
        return val.strip()
    return ""


def _fallback_mission(title: str | None) -> str:
    """
    Provide a consistent fallback mission if a template lacks one.
    Keep it very short and role-specific.
    """
    t = (title or "this role").strip()
    return f"As our {t}, you will help us ship meaningful value in your first 6–12 months."


def matched_role_editor(i, role, state, invoke_and_store_cb):
    """
    Renders an editor for one matched role:
      - Edits title/seniority/mission/skills/responsibilities
      - "Suggest with AI" (respects LLM cap; now hydrates mission too)
      - Apply changes (re-runs graph for this run only)
      - Save as reusable custom template (PERSISTS to data/role_knowledge_custom/)
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

    # Base template + role overrides
    tpl = load_template_for_role(role)
    must_tpl = field(role, "must_haves") or tpl.get("skills", {}).get("must", [])   # role overrides, else template
    nice_tpl = field(role, "nice_to_haves") or tpl.get("skills", {}).get("nice", [])
    resp_tpl = field(role, "responsibilities") or tpl.get("responsibilities", [])
    seniority = field(role, "seniority") or tpl.get("seniority", "Mid")
    # >>> NEW: mission (prefer role override, else template mission)
    mission_tpl = field(role, "mission") or tpl.get("mission") or _fallback_mission(title)

    # Function helps the suggester tailor content; default to template/function or "Engineering"
    function = tpl.get("function", "Engineering")

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
        mission_key = f"mission_{i}"
        ss = st.session_state

        # >>> Hydrate from any pending AI suggestion BEFORE creating widgets
        pending_key = f"pending_ai_matched_{i}"
        pending = ss.get(pending_key)
        if pending:
            ss[must_key] = pending.get("must", ss.get(must_key, ", ".join(must_tpl)))
            ss[nice_key] = pending.get("nice", ss.get(nice_key, ", ".join(nice_tpl)))
            ss[resp_key] = pending.get("resp", ss.get(resp_key, "\n".join(resp_tpl)))
            ss[mission_key] = pending.get("mission", ss.get(mission_key, mission_tpl))
            del ss[pending_key]

        # Defaults (only set if not already present)
        ss.setdefault(must_key, ", ".join(must_tpl))
        ss.setdefault(nice_key, ", ".join(nice_tpl))
        ss.setdefault(resp_key, "\n".join(resp_tpl))
        ss.setdefault(mission_key, mission_tpl)

        # ----- AI Suggestion (respects cap) -----
        gc = _get(state, "global_constraints", {}) or {}
        cap, used = int(gc.get("llm_cap", 0)), int(gc.get("llm_calls", 0))
        ai_disabled = used >= cap

        a, b = st.columns([1, 3])
        with a:
            if st.button("✨ Suggest with AI", key=f"regen_{i}", disabled=ai_disabled):
                title_in = ss.get(f"title_{i}", new_title)
                sen_in = ss.get(f"sen_{i}", new_sen)

                drafts = {
                    "mission": ss.get(f"mission_{i}", ""),
                    "must": ss.get(f"must_{i}", ""),               # comma string ok
                    "nice": ss.get(f"nice_{i}", ""),               # comma string ok
                    "responsibilities": ss.get(f"resp_{i}", ""),   # newline string ok
                }

                skills, meta = suggest_skills_with_meta(title_in, sen_in, function, drafts)

                ss[pending_key] = {
                    "must": _to_csv(skills.get("must")),
                    "nice": _to_csv(skills.get("nice")),
                    "resp": _to_lines(skills.get("responsibilities")),
                    "mission": (skills.get("mission") or _fallback_mission(title_in)),
                }

                last = ss.get("last_state")
                if last is not None:
                    ss["last_state"] = bump_llm_usage(last, meta, feature="skill_suggestion")
                st.rerun()
        with b:
            if cap:
                st.caption(f"LLM calls: {used}/{cap}")

        # ----- Textareas (bound to keys) -----
        # >>> NEW: mission editor (string)
        mission_s = st.text_area("Mission (one concise paragraph)", key=mission_key)
        must_s = st.text_area("Must-have skills (comma-separated)", key=must_key)
        nice_s = st.text_area("Nice-to-have skills (comma-separated)", key=nice_key)
        resp_s = st.text_area("Responsibilities (one per line)", key=resp_key)

        colx, coly = st.columns(2)

        # ----- Apply (this run only) -----
        with colx:
            if st.button("Apply changes for this plan", key=f"apply_{i}"):
                set_field(role, "title", (ss.get(f"title_{i}") or new_title).strip() or title)
                set_field(role, "seniority", ss.get(f"sen_{i}", new_sen))
                # >>> persist mission edit into the in-memory RoleSpec
                set_field(role, "mission", (mission_s or "").strip() or _fallback_mission(title))
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
                    "function": function,  # keep the same function as the template
                    "seniority": ss.get(f"sen_{i}", new_sen),
                    # >>> include mission so it persists to data/role_knowledge_custom/<slug>.json
                    "mission": (mission_s or "").strip() or _fallback_mission(title),
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
                # Mark as manual choice (no misleading score)
                set_field(role, "confidence", None)
                set_field(role, "confidence_source", "manual")

                # Re-run the graph so downstream JDs/plan pick up new template
                invoke_and_store_cb(state)
                st.success(f"Saved as custom template: {saved['title']}")
                changed = True
                st.rerun()

    return changed
