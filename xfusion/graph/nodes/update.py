from __future__ import annotations

from xfusion.domain.enums import InteractionState, StepStatus
from xfusion.graph.auditing import log_graph_event
from xfusion.graph.state import AgentGraphState


def update_node(state: AgentGraphState) -> AgentGraphState:
    """Refresh environment/memory/audit state."""
    if not state.plan:
        return state

    # Create audit record
    if state.current_step_id:
        step = next(
            (
                candidate
                for candidate in state.plan.steps
                if candidate.step_id == state.current_step_id
            ),
            None,
        )
        if step:
            log_graph_event(
                state,
                step=step,
                status=str(step.status),
                summary=state.response,
            )

    # Check if plan is complete or blocked
    if state.plan.interaction_state == InteractionState.EXECUTING:
        if all(s.status == StepStatus.SUCCESS for s in state.plan.steps):
            state.plan.interaction_state = InteractionState.COMPLETED
            state.plan.status = "completed"
        elif (
            any(s.status == StepStatus.FAILED for s in state.plan.steps)
            or state.plan.has_unexecutable_pending_steps()
        ):
            state.plan.interaction_state = InteractionState.FAILED
            state.plan.status = "failed"
            if state.plan.has_unexecutable_pending_steps():
                state.response = (
                    f"{state.response}\nPlan execution aborted: one or more dependencies failed."
                )

    return state
