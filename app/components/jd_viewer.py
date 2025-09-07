import streamlit as st

def render_jds(state):
    jds = getattr(state, "jds", {}) or {}
    jds_out = {k: (v.model_dump() if hasattr(v, "model_dump") else v) for k, v in jds.items()}
    for title, jd in jds_out.items():
        st.markdown(f"### {title}")
        st.json(jd)
