import streamlit as st
from services.state_helpers import _get, field
from services.graph_runner import invoke_and_store
from components.unresolved_role_panel import unresolved_role_panel
from components.matched_role_editor import matched_role_editor
from components.jd_viewer import render_jds

def render_roles_tab(state):
    st.subheader("Roles")
    roles = _get(state, "roles", []) or []

    def _invoke_and_store_wrapper(current_state):
        return invoke_and_store(current_state, st.session_state)

    unresolved = [(i, r) for i, r in enumerate(roles) if field(r, "status") in ("suggest", "unknown")]
    if unresolved:
        st.warning("Some roles need confirmation. Pick a suggestion or create a new role.")
        for idx, role in unresolved:
            did_change = unresolved_role_panel(idx, role, state, _invoke_and_store_wrapper)
            if did_change:
                st.rerun()
        st.info("Once you confirm all roles, the Job Descriptions, Plan, and Outreach Emails will be generated.")
        st.stop()

    matched = [r for r in roles if field(r, "status") == "match"]
    if not matched:
        st.info("No finalized roles yet.")
        return

    for i, role in enumerate(matched):
        if matched_role_editor(i, role, state, _invoke_and_store_wrapper):
            st.rerun()

    st.subheader("Job Descriptions")
    render_jds(state)
