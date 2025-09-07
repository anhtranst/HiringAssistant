# app/components/unresolved_role_panel.py
import streamlit as st
from datetime import datetime
from services.state_helpers import field, set_field, _get
from tools.role_matcher import load_kb, save_custom_role
from tools.search_stub import load_role_template
from tools.skill_suggester import suggest_skills_with_meta
from services.state_helpers import bump_llm_usage


def _parse_iso(ts: str | None):
    if not ts:
        return None
    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except Exception:
        return None


def unresolved_role_panel(idx, role, state, invoke_and_store_cb):
    """
    Panel for a single unresolved role phrase:
      - Shows top-3 suggestions (provided by matcher)
      - Defaults to the newest custom if available, else top score
      - Lets user preview and then apply a suggestion OR create a brand-new custom
    """
    changed = False
    title = field(role, "title", "Untitled role")
    status = field(role, "status", "unknown")
    suggestions = field(role, "suggestions", []) or []

    with st.expander(f"Resolve: {title}  ·  status={status}", expanded=True):
        # ---- Suggestions
        def _suggest_label(s):
            tag = "CUSTOM" if s.get("is_custom") else "CORE"
            ts = s.get("created_at")
            ts_short = ""
            dt = _parse_iso(ts)
            if dt:
                ts_short = dt.strftime("%Y-%m-%d %H:%M")
            extra = f" · {tag}" + (f" · {ts_short}" if ts_short else "")
            return f"{s['title']} (score {s['score']:.2f}){extra}"

        default_idx = 0
        newest_dt, newest_idx = None, None
        for i, s in enumerate(suggestions):
            if s.get("is_custom") and s.get("created_at"):
                dt = _parse_iso(s["created_at"])
                if dt and (newest_dt is None or dt > newest_dt):
                    newest_dt, newest_idx = dt, i
        if newest_idx is not None:
            default_idx = newest_idx

        labels = [_suggest_label(s) for s in suggestions]
        choice_label = None
        if labels:
            choice_label = st.radio(
                "Choose a suggested role template:",
                labels,
                index=default_idx,
                key=f"suggest_choice_{idx}",
            )
        else:
            st.info("No suggestions found for this phrase.")

        # ---- Use selected suggestion (right below the radio)
        if labels:
            use_now = st.button(
                "Use selected suggestion",
                key=f"use_suggest_{idx}",
                type="primary",
                disabled=not choice_label,
            )
            if use_now and choice_label:
                s = suggestions[labels.index(choice_label)]
                kb = load_kb()
                rec = next((r for r in kb if r["id"] == s["role_id"]), None)

                # Patch RoleSpec in place
                set_field(role, "role_id", s["role_id"])
                set_field(role, "title", rec["title"] if rec else s["title"])
                set_field(role, "status", "match")
                set_field(role, "confidence", float(s["score"]))
                set_field(role, "file", rec["file"] if rec else None)
                set_field(role, "suggestions", [])

                invoke_and_store_cb(state)
                changed = True
                st.rerun()

        # ---- Preview of the selected suggestion
        if choice_label:
            s = suggestions[labels.index(choice_label)]
            kb = load_kb()
            rec = next((r for r in kb if r["id"] == s["role_id"]), None)
            if rec:
                tpl = load_role_template(rec["file"])
                must = tpl.get("skills", {}).get("must", []) or []
                nice = tpl.get("skills", {}).get("nice", []) or []
                resp = tpl.get("responsibilities", []) or []
                fn = tpl.get("function") or rec.get("function")
                sen = tpl.get("seniority") or rec.get("seniority")

                with st.container(border=True):
                    st.caption("Template preview")
                    left, right = st.columns(2)
                    with left:
                        st.markdown(f"**Function:** {fn or '—'}")
                        st.markdown(f"**Seniority:** {sen or '—'}")
                        st.markdown("**Must-have skills:**")
                        st.write(", ".join(must) if must else "—")
                        st.markdown("**Nice-to-have skills:**")
                        st.write(", ".join(nice) if nice else "—")
                    with right:
                        st.markdown("**Responsibilities:**")
                        st.write("\n".join(resp) if resp else "—")

        # ---- Create a new role
        st.markdown("**Or create a new role**")
        with st.form(f"create_role_form_{idx}", clear_on_submit=False):
            new_title = st.text_input("Title", value=title, key=f"crt_title_{idx}")
            function = st.selectbox(
                "Function", ["Engineering", "Data", "Design", "GTM", "Operations"], index=0, key=f"crt_fn_{idx}"
            )
            seniority = st.selectbox(
                "Seniority", ["Intern", "Junior", "Mid", "Senior", "Staff", "Principal", "Lead"],
                index=3, key=f"crt_sen_{idx}"
            )

            # Keys for text areas
            must_key, nice_key, resp_key = f"crt_must_{idx}", f"crt_nice_{idx}", f"crt_resp_{idx}"

            # ----- AI-suggest pending buffer: hydrate BEFORE creating widgets
            pending_key = f"pending_ai_{idx}"
            pending = st.session_state.get(pending_key)
            if pending:
                # Always set values BEFORE widget instantiation (safe even if keys already exist)
                st.session_state[must_key] = pending.get("must", "")
                st.session_state[nice_key] = pending.get("nice", "")
                st.session_state[resp_key]  = pending.get("resp", "")
                del st.session_state[pending_key]

            # Ensure defaults exist before widget instantiation (no-ops if already set)
            st.session_state.setdefault(must_key, "")
            st.session_state.setdefault(nice_key, "")
            st.session_state.setdefault(resp_key, "")

            # Now create the widgets bound to those keys
            must = st.text_area("Must-have skills (comma-separated)", key=must_key)
            nice = st.text_area("Nice-to-have skills (comma-separated)", key=nice_key)
            resp = st.text_area("Responsibilities (one per line)", key=resp_key)

            # Buttons at the bottom, side by side
            col1, col2 = st.columns([1, 1])
            with col1:
                gc = _get(state, "global_constraints", {}) or {}
                cap = int(gc.get("llm_cap", 0))
                used = int(gc.get("llm_calls", 0))
                ai_disabled = used >= cap
                suggest_ai = st.form_submit_button("✨ Suggest with AI", disabled=ai_disabled)
            with col2:
                disable_create = (
                    not new_title.strip()
                    or not must.strip()
                    or not nice.strip()
                    or not resp.strip()
                )
                submit_new = st.form_submit_button("Create this custom role", disabled=disable_create)

            # Actions after buttons
            if suggest_ai:
                # Get suggestions and stash in pending buffer; rerun to hydrate safely
                title_in = st.session_state.get(f"crt_title_{idx}", new_title)
                sen_in = st.session_state.get(f"crt_sen_{idx}", seniority)
                skills, meta = suggest_skills_with_meta(title_in, sen_in)

                st.session_state[pending_key] = {
                    "must": ", ".join(skills.get("must", [])),
                    "nice": ", ".join(skills.get("nice", [])),
                    "resp": "\n".join(skills.get("responsibilities", [])),
                }
                last = st.session_state.get("last_state")
                if last is not None:
                    st.session_state["last_state"] = bump_llm_usage(last, meta, feature="skill_suggestion")
                st.rerun()

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
                    "sourcing_tags": [],
                }
                saved = save_custom_role(payload)
                # Patch RoleSpec so current session uses the brand-new template
                set_field(role, "role_id", saved["id"])
                set_field(role, "title", saved["title"])
                set_field(role, "file", saved["file"])
                set_field(role, "status", "match")
                set_field(role, "confidence", 1.0)
                set_field(role, "suggestions", [])
                invoke_and_store_cb(state)
                st.success(f"Created and applied custom role: {saved['title']}")
                changed = True
                st.rerun()

    return changed
