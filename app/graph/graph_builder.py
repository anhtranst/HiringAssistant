from langgraph.graph import StateGraph
from graph.state import AppState
from graph.nodes import node_intake, node_profile, node_jd, node_plan


def build_graph():
    g = StateGraph(AppState)
    g.add_node("intake", node_intake)
    g.add_node("profile", node_profile)
    g.add_node("jd", node_jd)
    g.add_node("plan", node_plan)

    g.set_entry_point("intake")
    g.add_edge("intake", "profile")
    g.add_edge("profile", "jd")
    g.add_edge("jd", "plan")

    return g.compile()
