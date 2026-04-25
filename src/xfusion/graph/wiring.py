from __future__ import annotations

from typing import Any

from langgraph.graph import END, StateGraph

from xfusion.graph.nodes.confirm import confirm_node
from xfusion.graph.nodes.disambiguate import disambiguate_node
from xfusion.graph.nodes.execute import execute_node
from xfusion.graph.nodes.parse import parse_node
from xfusion.graph.nodes.plan import plan_node
from xfusion.graph.nodes.policy import policy_node
from xfusion.graph.nodes.respond import respond_node
from xfusion.graph.nodes.update import update_node
from xfusion.graph.nodes.validate import validate_node
from xfusion.graph.nodes.verify import verify_node
from xfusion.graph.state import AgentGraphState


def route_after_parse(state: AgentGraphState) -> str:
    """Route after parsing."""
    if state.plan and state.plan.interaction_state == "awaiting_confirmation":
        return "confirm"
    if state.plan and state.plan.interaction_state == "awaiting_disambiguation":
        return "disambiguate"
    return "plan"


def route_after_policy(state: AgentGraphState) -> str:
    """Route after policy evaluation."""
    if not state.plan:
        return "respond"

    if state.plan.interaction_state in {"refused", "failed", "aborted"}:
        return "respond"

    if state.plan.interaction_state == "awaiting_confirmation":
        return "respond"

    step = state.plan.next_executable_step()
    if not step:
        return "respond"

    return "execute"


def route_after_validate(state: AgentGraphState) -> str:
    """Route after mandatory static validation."""
    if not state.plan:
        return "respond"

    if state.plan.interaction_state in {"failed", "refused", "aborted"}:
        return "respond"

    return "policy"


def route_after_update(state: AgentGraphState) -> str:
    """Route after state update to decide if we need more steps."""
    if not state.plan:
        return "respond"

    if state.plan.interaction_state in {"completed", "failed", "aborted", "refused"}:
        return "respond"

    return "validate"


def build_agent_graph(registry: Any) -> StateGraph:
    """Build the XFusion LangGraph workflow."""

    # Create wrapped nodes to inject dependencies if needed
    def execute_node_wrapped(state: AgentGraphState):
        return execute_node(state, registry=registry)

    graph = StateGraph(AgentGraphState)

    graph.add_node("parse", parse_node)
    graph.add_node("disambiguate", disambiguate_node)
    graph.add_node("plan", plan_node)
    graph.add_node("validate", validate_node)
    graph.add_node("policy", policy_node)
    graph.add_node("confirm", confirm_node)
    graph.add_node("execute", execute_node_wrapped)
    graph.add_node("verify", verify_node)
    graph.add_node("update", update_node)
    graph.add_node("respond", respond_node)

    graph.set_entry_point("parse")

    graph.add_conditional_edges(
        "parse",
        route_after_parse,
        {"confirm": "confirm", "disambiguate": "disambiguate", "plan": "plan"},
    )

    graph.add_edge("disambiguate", "plan")
    graph.add_edge("plan", "validate")

    graph.add_conditional_edges(
        "validate", route_after_validate, {"policy": "policy", "respond": "respond"}
    )

    graph.add_conditional_edges(
        "policy", route_after_policy, {"execute": "execute", "respond": "respond"}
    )

    graph.add_conditional_edges(
        "confirm",
        lambda x: "execute" if x.plan.interaction_state == "executing" else "respond",
        {"execute": "execute", "respond": "respond"},
    )
    graph.add_edge("execute", "verify")
    graph.add_edge("verify", "update")

    graph.add_conditional_edges(
        "update", route_after_update, {"validate": "validate", "respond": "respond"}
    )

    graph.add_edge("respond", END)

    return graph
