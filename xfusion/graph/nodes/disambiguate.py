from __future__ import annotations

from xfusion.domain.enums import InteractionState
from xfusion.graph.state import AgentGraphState


def disambiguate_node(state: AgentGraphState) -> AgentGraphState:
    """Set awaiting_disambiguation when target/scope/risk boundary is unclear."""
    if not state.plan:
        return state

    if state.plan.interaction_state == InteractionState.AWAITING_DISAMBIGUATION:
        # If we were already awaiting disambiguation, the new input should help.
        # For this prototype, we'll just move back to planning.
        state.plan = None

    return state
