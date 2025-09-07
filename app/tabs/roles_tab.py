import streamlit as st
from services.state_helpers import _get, field
from services.graph_runner import invoke_and_store
from components.unresolved_role_panel import unresolved_role_panel
from components.matched_role_editor import matched_role_editor
from components.jd_viewer import render_jds


def render_roles_tab(state):
    st.subheader("Roles")
    roles = _get(state, "roles", []) or []

    # Heavy runner: re-runs the LangGraph, updates outputs (JDs/plan), and clears "stale" flag.
    def _invoke_and_store_wrapper(current_state):
        out = invoke_and_store(current_state, st.session_state)
        try:
            gc = _get(out, "global_constraints", {}) or {}
            gc["plan_stale"] = False  # outputs are now fresh
            out.global_constraints = gc
            st.session_state["last_state"] = out
        except Exception:
            pass
        return out

    # Lightweight saver: store only; mark outputs as stale. Use this during role resolution and editing.
    def _store_only_wrapper(current_state):
        gc = _get(current_state, "global_constraints", {}) or {}
        gc["plan_stale"] = True  # downstream JDs/plan should be rebuilt later
        current_state.global_constraints = gc
        st.session_state["last_state"] = current_state
        return current_state

    # -------------------------
    # Unresolved roles: resolve with store-only (no heavy recompute per click)
    # -------------------------
    unresolved = [(i, r) for i, r in enumerate(roles) if field(r, "status") in ("suggest", "unknown")]
    if unresolved:
        st.warning("Some roles need confirmation. Pick a suggestion or create a new role.")

        for idx, role in unresolved:
            did_change = unresolved_role_panel(idx, role, state, _store_only_wrapper)
            if did_change:
                st.rerun()

        st.info("Once you confirm all roles, click **Generate plan & JDs** to build everything in one go.")
        st.stop()

    # -------------------------
    # All matched: allow editing (still store-only) and show one rebuild button
    # -------------------------
    matched = [r for r in roles if field(r, "status") == "match"]
    if not matched:
        st.info("No finalized roles yet.")
        return

    gc = _get(state, "global_constraints", {}) or {}
    plan_stale = bool(gc.get("plan_stale"))

    # CTA to rebuild all outputs once
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
            # Edits saved; mark as stale already (done in wrapper), just re-render UI
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
