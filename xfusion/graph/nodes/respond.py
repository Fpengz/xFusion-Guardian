from __future__ import annotations

from xfusion.domain.enums import InteractionState
from xfusion.graph.state import AgentGraphState


def respond_node(state: AgentGraphState) -> AgentGraphState:
    """Format final or intermediate response."""
    if not state.plan:
        return state

    if state.plan.interaction_state == InteractionState.COMPLETED:
        state.response = f"Task completed successfully: {state.plan.goal}\n\n" + state.response
    elif state.plan.interaction_state == InteractionState.REFUSED:
        state.response = f"I cannot proceed: {state.response}"
    elif state.plan.interaction_state == InteractionState.AWAITING_CONFIRMATION:
        # Response is already set in policy_node
        pass

    return state
