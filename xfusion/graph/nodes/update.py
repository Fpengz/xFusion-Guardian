from __future__ import annotations

from xfusion.domain.enums import InteractionState, StepStatus
from xfusion.graph.auditing import log_graph_event
from xfusion.graph.state import AgentGraphState


def update_node(state: AgentGraphState) -> AgentGraphState:
    """Refresh environment/memory/audit state."""
    if not state.plan:
        return state

    dependency_abort = False
    if state.plan.interaction_state == InteractionState.EXECUTING and (
        any(s.status == StepStatus.FAILED for s in state.plan.steps)
        or state.plan.has_unexecutable_pending_steps()
    ):
        state.plan.interaction_state = InteractionState.FAILED
        state.plan.status = "failed"
        dependency_abort = state.plan.has_unexecutable_pending_steps()
        if dependency_abort:
            state.response = (
                f"{state.response}\nPlan execution aborted: one or more dependencies failed."
            )

    # Create audit record from authoritative post-transition state.
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
            if step.status == StepStatus.SUCCESS:
                step.authorized_output_accepted = True
                state.authorized_step_outputs[step.step_id] = state.step_outputs.get(
                    step.step_id, {}
                )
            audit_status = step.failure_class or str(step.status)
            log_graph_event(
                state,
                step=step,
                status=audit_status,
                summary=state.response,
            )

    # Check if plan is complete.
    if state.plan.interaction_state == InteractionState.EXECUTING and all(
        s.status == StepStatus.SUCCESS for s in state.plan.steps
    ):
        state.plan.interaction_state = InteractionState.COMPLETED
        state.plan.status = "completed"

    return state
