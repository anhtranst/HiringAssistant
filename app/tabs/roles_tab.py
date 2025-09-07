# app/tabs/roles_tab.py
import re
import difflib
import streamlit as st

from services.state_helpers import _get, field
from services.graph_runner import invoke_and_store

from components.unresolved_role_panel import unresolved_role_panel
from components.matched_role_editor import matched_role_editor
from components.jd_viewer import render_jds

# Use the existing KB loader so we can offer top-3 suggestions for newly added roles.
from tools.role_matcher import load_kb


# -----------------------------
# Local helpers
# -----------------------------

def _store_only_wrapper(current_state):
    """
    Lightweight persistence: update session state WITHOUT re-running the graph.
    Also mark the downstream outputs (JDs/plan) as stale, so the UI can show the
    'Generate plan & JDs' CTA when appropriate.
    """
    gc = _get(current_state, "global_constraints", {}) or {}
    gc["plan_stale"] = True
    try:
        current_state.global_constraints = gc
    except Exception:
        current_state["global_constraints"] = gc
    st.session_state["last_state"] = current_state
    return current_state


def _invoke_and_store_wrapper(current_state):
    """
    Heavy runner: re-run the LangGraph to rebuild JDs/plan.
    Clears the stale flag after a successful rebuild.
    """
    out = invoke_and_store(current_state, st.session_state)
    try:
        gc = _get(out, "global_constraints", {}) or {}
        gc["plan_stale"] = False
        out.global_constraints = gc
        st.session_state["last_state"] = out
    except Exception:
        pass
    return out


def _normalize_title(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").strip())


def _score_title(query: str, candidate: str, aliases=None) -> float:
    """
    Very small, non-LLM ranker:
    - Compare against title and aliases and return the best similarity score (0..1).
    - SequenceMatcher works fine for short titles; cheap and good enough here.
    """
    q = _normalize_title(query).lower()
    if not q:
        return 0.0

    cands = [candidate or ""]
    if isinstance(aliases, list):
        cands.extend([a for a in aliases if isinstance(a, str)])

    best = 0.0
    for c in cands:
        c_norm = _normalize_title(c).lower()
        if not c_norm:
            continue
        score = difflib.SequenceMatcher(None, q, c_norm).ratio()
        if score > best:
            best = score
    return float(best)


def _suggest_from_kb(title: str, exclude_ids: set[str] | None = None, top_k: int = 3):
    """
    Use the existing KB (core + custom) to produce top-k suggestions for a new role title.
    No LLM calls. Returns a list of suggestion dicts:
    [
      {
        "role_id": str,
        "title": str,
        "score": float,
        "is_custom": bool,
        "created_at": str|None
      },
      ...
    ]
    (Other keys like skills/responsibilities are intentionally omitted here.)
    """
    exclude_ids = exclude_ids or set()
    kb = load_kb()  # each rec: id, title, file, function, seniority, aliases, created_at (for custom), ...
    scored = []
    for rec in kb:
        rid = rec.get("id")
        if not rid or rid in exclude_ids:
            continue
        score = _score_title(title, rec.get("title", ""), rec.get("aliases"))
        if score <= 0:
            continue
        is_custom = bool("__custom__" in (rec.get("file") or ""))
        scored.append({
            "role_id": rid,
            "title": rec.get("title"),
            "score": score,
            "is_custom": is_custom,
            "created_at": rec.get("created_at"),
            # (Optional) You could include function/seniority here, but the panel loads from file anyway.
        })

    scored.sort(key=lambda x: x["score"], reverse=True)
    return scored[:top_k]


def _safe_assign_roles(state, roles_list):
    """Assign updated roles back to the state, handling dict/model cases."""
    try:
        state.roles = roles_list
    except Exception:
        state["roles"] = roles_list


# -----------------------------
# Main tab renderer
# -----------------------------

def render_roles_tab(state):
    st.subheader("Roles")

    # Always present a global 'Add a role' entry point at the top of the tab.
    # This supports the two real-world cases:
    #  - HR changes their mind and wants *another* role
    #  - Intake under-detected the roles in the prompt; HR adds the missing one
    with st.expander("➕ Add a role", expanded=False):
        with st.form("add_role_form", clear_on_submit=False):
            title_in = st.text_input("Role title *", placeholder="e.g., Data Analyst", key="add_role_title")
            function_in = st.selectbox("Function", ["unspecified", "Engineering", "Data", "Design", "GTM", "Operations"], index=0, key="add_role_fn")
            seniority_in = st.selectbox("Seniority", ["Intern", "Junior", "Mid", "Senior", "Staff", "Principal", "Lead"], index=2, key="add_role_sen")
            submitted = st.form_submit_button("Add role")

        if submitted:
            role_title = _normalize_title(title_in)
            if not role_title:
                st.warning("Please enter a role title.")
            else:
                # Compute exclude set so we don't suggest templates already chosen elsewhere.
                used_ids = set()
                for r in (_get(state, "roles", []) or []):
                    if field(r, "status") == "match":
                        rid = field(r, "role_id")
                        if rid:
                            used_ids.add(rid)

                suggestions = _suggest_from_kb(role_title, exclude_ids=used_ids, top_k=3)

                # Append a new unresolved role (status='suggest'), so the resolver takes over.
                roles = (_get(state, "roles", []) or []).copy()
                roles.append({
                    "title": role_title,
                    "function": None if function_in == "unspecified" else function_in,
                    "seniority": seniority_in,
                    "status": "suggest",
                    "suggestions": suggestions,
                    # Other fields (role_id, file, etc.) are chosen in the resolver.
                })
                _safe_assign_roles(state, roles)

                # Store-only and mark plan as stale; this will cause the resolver to render.
                _store_only_wrapper(state)
                st.success(f"Added role **{role_title}**. Please pick a template or create a custom role below.")
                st.rerun()

    # From here, render unresolved/matched flows (same behavior as our on-demand rebuild design).

    roles = _get(state, "roles", []) or []

    # --- Unresolved roles: resolve with store-only (no heavy recompute per click)
    unresolved = [(i, r) for i, r in enumerate(roles) if field(r, "status") in ("suggest", "unknown")]
    if unresolved:
        st.warning("Some roles need confirmation. Pick a suggestion or create a new role.")
        for idx, role in unresolved:
            did_change = unresolved_role_panel(idx, role, state, _store_only_wrapper)
            if did_change:
                st.rerun()

        st.info("Once you confirm all roles, click **Generate plan & JDs** to build everything in one go.")
        st.stop()

    # --- All matched: allow editing (still store-only) and show one rebuild button
    matched = [r for r in roles if field(r, "status") == "match"]
    if not matched:
        st.info("No finalized roles yet.")
        return

    gc = _get(state, "global_constraints", {}) or {}
    plan_stale = bool(gc.get("plan_stale"))

    if plan_stale:
        st.info("Changes pending. Click to rebuild the plan and JDs.")
        if st.button("🔁 Generate plan & JDs", type="primary", key="regen_all"):
            _invoke_and_store_wrapper(state)
            st.rerun()
    else:
        st.success("Plan & JDs are up to date. Edit roles below to make changes.")

    # Editors for matched roles — use store-only so we don't rebuild per edit
    for i, role in enumerate(matched):
        if matched_role_editor(i, role, state, _store_only_wrapper):
            st.rerun()

    st.subheader("Job Descriptions")
    if plan_stale:
        st.caption("⚠️ Showing the last built JDs. Click **Generate plan & JDs** to refresh.")
    render_jds(state)

    # Optional second CTA at bottom for convenience
    if plan_stale:
        st.divider()
        if st.button("🔁 Generate plan & JDs", type="primary", key="regen_all_bottom"):
            _invoke_and_store_wrapper(state)
            st.rerun()
