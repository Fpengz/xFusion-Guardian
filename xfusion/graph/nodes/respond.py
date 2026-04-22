from __future__ import annotations

from xfusion.graph.response import format_agent_response
from xfusion.graph.state import AgentGraphState


def respond_node(state: AgentGraphState) -> AgentGraphState:
    """Format final or intermediate response."""
    if not state.plan:
        return state

    state.response = format_agent_response(state)
    return state
