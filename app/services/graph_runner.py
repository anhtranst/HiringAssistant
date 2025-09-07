# app/services/graph_runner.py
from pydantic import ValidationError
from graph.graph_builder import build_graph
from graph.state import AppState

def invoke_and_store(state, session_state):
    graph = build_graph()
    result = graph.invoke(state)
    if isinstance(result, dict):
        try:
            result = AppState(**result)
        except ValidationError:
            pass
    session_state["last_state"] = result
    return result
