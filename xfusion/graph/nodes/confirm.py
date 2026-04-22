from __future__ import annotations

from xfusion.domain.enums import InteractionState
from xfusion.graph.auditing import log_graph_event
from xfusion.graph.state import AgentGraphState


def confirm_node(state: AgentGraphState) -> AgentGraphState:
    """Handle pause for exact typed confirmation when required."""
    if not state.plan or state.plan.interaction_state != InteractionState.AWAITING_CONFIRMATION:
        return state

    step = state.plan.next_executable_step()
    if not step:
        return state

    expected = (step.confirmation_phrase or "").strip()
    actual = state.user_input.strip()

    if expected and actual == expected:
        state.plan.interaction_state = InteractionState.EXECUTING
        step.requires_confirmation = False
        state.response = "Confirmation received. Proceeding..."
        log_graph_event(state, step=step, status="confirmed", summary=state.response)
    else:
        state.plan.interaction_state = InteractionState.ABORTED
        state.plan.status = "aborted"
        state.response = (
            f"Action aborted: Input did not match required confirmation phrase '{expected}'."
        )
        log_graph_event(state, step=step, status="aborted", summary=state.response)

    # Requirements: Confirmation must be cleared after one use.
    state.pending_confirmation_phrase = None
    step.confirmation_phrase = None

    return state
