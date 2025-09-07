# app/components/unresolved_role_panel.py
import streamlit as st
from datetime import datetime
from services.state_helpers import field, set_field, _get
from tools.role_matcher import load_kb, save_custom_role
from tools.search_stub import load_role_template
from tools.skill_suggester import suggest_skills_with_meta
from services.state_helpers import bump_llm_usage

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

def _parse_iso(ts: str | None):
    """
    Parse ISO timestamps while being tolerant of 'Z' suffix.
    Returns a datetime or None.
    """
    if not ts:
        return None
    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except Exception:
        return None


def _fallback_mission(title: str | None) -> str:
    """
    Provide a consistent fallback mission if a template lacks one.
    Keep it very short and role-specific.
    """
    t = (title or "this role").strip()
    return f"As our {t}, you will help us ship meaningful value in your first 6–12 months."


def unresolved_role_panel(idx, role, state, invoke_and_store_cb):
    """
    Panel for a single unresolved role phrase:
      - Shows top-3 suggestions (provided by matcher)
      - Defaults to the newest custom if available, else top score
      - Preview updates immediately on selection (no extra button)
      - Prevents picking the same template (role_id) in multiple slots by
        excluding already-chosen templates from this panel's suggestions
      - Apply selection OR create a brand-new custom role
      - NEW: Show mission in preview; allow mission input for custom roles
      - NEW: 'Suggest with AI' now hydrates Mission via tools/skill_suggester
    """
    changed = False
    title = field(role, "title", "Untitled role")
    status = field(role, "status", "unknown")

    # Raw suggestions from matcher
    raw_suggestions = field(role, "suggestions", []) or []

    # ----- Exclude templates already chosen in OTHER roles -----
    used_ids = set()
    all_roles = _get(state, "roles", []) or []
    for i, r in enumerate(all_roles):
        if i == idx:
            continue  # don't consider current panel
        if field(r, "status") == "match":
            rid = field(r, "role_id")
            if rid:
                used_ids.add(rid)

    # Filter suggestions to avoid duplicates
    suggestions = [s for s in raw_suggestions if s.get("role_id") not in used_ids]
    excluded_count = len(raw_suggestions) - len(suggestions)

    with st.expander(f"Resolve: {title}  ·  status={status}", expanded=True):

        # Optional hint if we hid some options
        if excluded_count > 0:
            st.caption(
                f"({excluded_count} suggestion{'s' if excluded_count > 1 else ''} hidden because that template is already chosen for another role.)"
            )

        # ---- Pretty label builder (display only)
        def _suggest_label(s):
            tag = "CUSTOM" if s.get("is_custom") else "CORE"
            ts = s.get("created_at")
            ts_short = ""
            dt = _parse_iso(ts)
            if dt:
                ts_short = dt.strftime("%Y-%m-%d %H:%M")
            extra = f" · {tag}" + (f" · {ts_short}" if ts_short else "")
            return f"{s.get('title', '—')} (score {s.get('score', 0):.2f}){extra}"

        # ---- Choose default as newest custom (if any) among the FILTERED suggestions
        default_idx = 0
        newest_dt, newest_idx = None, None
        for i, s in enumerate(suggestions):
            if s.get("is_custom") and s.get("created_at"):
                dt = _parse_iso(s["created_at"])
                if dt and (newest_dt is None or dt > newest_dt):
                    newest_dt, newest_idx = dt, i
        if newest_idx is not None:
            default_idx = newest_idx

        # ---- Dropdown with STABLE integer options; fully controlled by session_state
        selected_idx_key = f"suggest_choice_idx_{idx}"
        if suggestions:
            # If selection existed but points past the filtered list, reset it
            if (selected_idx_key in st.session_state) and (
                st.session_state[selected_idx_key] is None
                or st.session_state[selected_idx_key] >= len(suggestions)
            ):
                st.session_state[selected_idx_key] = default_idx

            # Initialize once if not present
            if selected_idx_key not in st.session_state:
                st.session_state[selected_idx_key] = default_idx

            # Controlled widget: bind to key (no index param)
            st.selectbox(
                "Choose a suggested role template:",
                options=list(range(len(suggestions))),  # stable values (0..N-1)
                key=selected_idx_key,
                format_func=lambda i: _suggest_label(suggestions[i]),
            )
            selected_idx = st.session_state[selected_idx_key]
        else:
            st.info(
                "No suggestions available for this phrase (duplicates removed or none matched)."
            )
            selected_idx = None

        # ---- Primary CTA (right below the chooser)
        if selected_idx is not None:
            if st.button("Use selected suggestion", key=f"use_suggest_{idx}", type="primary"):
                s = suggestions[selected_idx]
                kb = load_kb()
                rec = next((r for r in kb if r["id"] == s["role_id"]), None)

                # Patch RoleSpec in place (mark as manual pick)
                set_field(role, "role_id", s["role_id"])
                set_field(role, "title", (rec["title"] if rec else s.get("title")) or title)
                set_field(role, "status", "match")
                set_field(role, "confidence", None)  # ← no misleading score
                set_field(role, "confidence_source", "manual")  # ← mark manual
                set_field(role, "file", rec["file"] if rec else None)
                set_field(role, "suggestions", [])

                invoke_and_store_cb(state)
                changed = True
                st.rerun()

        # ---- Preview of the currently selected suggestion (auto-updates)
        if selected_idx is not None:
            s = suggestions[selected_idx]
            kb = load_kb()
            rec = next((r for r in kb if r["id"] == s["role_id"]), None)

            # Mission + core fields with safe fallbacks
            if rec:
                tpl = load_role_template(rec["file"])
                mission = tpl.get("mission")  # string mission stored in role JSON
                must = tpl.get("skills", {}).get("must", []) or []
                nice = tpl.get("skills", {}).get("nice", []) or []
                resp = tpl.get("responsibilities", []) or []
                fn = tpl.get("function") or rec.get("function")
                sen = tpl.get("seniority") or rec.get("seniority")
                preview_title = tpl.get("title") or rec.get("title") or s.get("title") or title
            else:
                skills = s.get("skills", {}) or {}
                mission = s.get("mission")  # suggestions may or may not carry mission
                must = skills.get("must", []) or []
                nice = skills.get("nice", []) or []
                resp = s.get("responsibilities", []) or []
                fn = s.get("function")
                sen = s.get("seniority")
                preview_title = s.get("title") or title

            with st.container(border=True):
                st.caption("Template preview")
                # --- NEW: Mission shown at the top of the preview
                st.markdown("**Mission:**")
                st.write(mission or _fallback_mission(preview_title))

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
                    # Using newline join to render bullet-like lines without markdown bullets,
                    # which keeps formatting consistent with your original approach.
                    st.write("\n".join(resp) if resp else "—")

        # ---- Create a new role
        st.markdown("**Or create a new role**")
        with st.form(f"create_role_form_{idx}", clear_on_submit=False):
            new_title = st.text_input("Title", value=title, key=f"crt_title_{idx}")

            function = st.selectbox(
                "Function",
                ["Engineering", "Data", "Design", "GTM", "Operations"],
                index=0,
                key=f"crt_fn_{idx}",
            )
            seniority = st.selectbox(
                "Seniority",
                ["Intern", "Junior", "Mid", "Senior", "Staff", "Principal", "Lead"],
                index=3,
                key=f"crt_sen_{idx}",
            )

            # Keys for text areas
            must_key, nice_key, resp_key = (
                f"crt_must_{idx}",
                f"crt_nice_{idx}",
                f"crt_resp_{idx}",
            )
            mission_key = f"crt_mission_{idx}"

            # ----- AI-suggest pending buffer: hydrate BEFORE creating widgets
            # IMPORTANT: we must hydrate session_state BEFORE instantiating widgets with those keys.
            pending_key = f"pending_ai_{idx}"
            pending = st.session_state.get(pending_key)
            if pending:
                st.session_state[must_key] = pending.get("must", "")
                st.session_state[nice_key] = pending.get("nice", "")
                st.session_state[resp_key] = pending.get("resp", "")
                st.session_state[mission_key] = pending.get("mission", "")
                del st.session_state[pending_key]

            # Ensure defaults exist before widget instantiation
            st.session_state.setdefault(must_key, "")
            st.session_state.setdefault(nice_key, "")
            st.session_state.setdefault(resp_key, "")
            st.session_state.setdefault(mission_key, "")  # ← ensure mission default too

            # --- Mission input (string-based) — created AFTER hydration
            mission_text = st.text_area(
                "Mission (one concise paragraph)",
                key=mission_key,
                placeholder=f"As our {new_title or 'role'}, you will …",
            )

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
                # Require mission as well for cleaner JD output later
                disable_create = (
                    not new_title.strip()
                    or not mission_text.strip()
                    or not must.strip()
                    or not nice.strip()
                    or not resp.strip()
                )
                submit_new = st.form_submit_button(
                    "Create this custom role", disabled=disable_create
                )

            # Actions after buttons
            if suggest_ai:
                title_in = st.session_state.get(f"crt_title_{idx}", new_title)
                sen_in = st.session_state.get(f"crt_sen_{idx}", seniority)
                fn_in = st.session_state.get(f"crt_fn_{idx}", function)

                # Collect drafts from current widgets
                drafts = {
                    "mission": st.session_state.get(f"crt_mission_{idx}", ""),
                    "must": st.session_state.get(f"crt_must_{idx}", ""),  # comma string is OK
                    "nice": st.session_state.get(f"crt_nice_{idx}", ""),  # comma string is OK
                    "responsibilities": st.session_state.get(f"crt_resp_{idx}", ""),  # newline string is OK
                }

                # Context-aware suggestion
                skills, meta = suggest_skills_with_meta(title_in, sen_in, fn_in, drafts)

                st.session_state[pending_key] = {
                    "must": _to_csv(skills.get("must")),
                    "nice": _to_csv(skills.get("nice")),
                    "resp": _to_lines(skills.get("responsibilities")),
                    "mission": (skills.get("mission") or _fallback_mission(title_in)),
                }


                # LLM usage accounting/logging for the skills suggestion tool
                last = st.session_state.get("last_state")
                if last is not None:
                    st.session_state["last_state"] = bump_llm_usage(
                        last, meta, feature="skill_suggestion"
                    )
                st.rerun()

            if submit_new:
                # Default loop remains the same; you can later make this configurable
                loop_default = [
                    "Screen",
                    "Tech Deep-Dive",
                    "System Design",
                    "Founder Chat",
                    "References",
                ]
                payload = {
                    "title": new_title.strip(),
                    "function": function,
                    "seniority": seniority,
                    "mission": mission_text.strip(),  # ← include mission in saved role
                    "aliases": [],
                    "skills": {
                        "must": [s.strip() for s in must.split(",") if s.strip()],
                        "nice": [s.strip() for s in nice.split(",") if s.strip()],
                    },
                    "responsibilities": [
                        ln.strip() for ln in resp.splitlines() if ln.strip()
                    ],
                    "interview_loop": loop_default,
                    "sourcing_tags": [],
                }
                saved = save_custom_role(payload)

                # Patch RoleSpec so current session uses the brand-new template
                set_field(role, "role_id", saved["id"])
                set_field(role, "title", saved["title"])
                set_field(role, "file", saved["file"])
                set_field(role, "status", "match")

                # Mark as manual choice (no misleading score)
                set_field(role, "confidence", None)
                set_field(role, "confidence_source", "manual")
                set_field(role, "suggestions", [])

                invoke_and_store_cb(state)
                st.success(f"Created and applied custom role: {saved['title']}")
                changed = True
                st.rerun()

    return changed
