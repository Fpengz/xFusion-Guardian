from __future__ import annotations

from datetime import datetime

from xfusion.domain.enums import InteractionState, StepStatus
from xfusion.graph.state import AgentGraphState


def update_node(state: AgentGraphState) -> AgentGraphState:
    """Refresh environment/memory/audit state."""
    if not state.plan:
        return state

    # Create audit record
    if state.current_step_id:
        record = {
            "timestamp": datetime.now().isoformat(),
            "plan_id": state.plan.plan_id,
            "step_id": state.current_step_id,
            "interaction_state": state.plan.interaction_state,
            "verification_result": state.verification_result.model_dump()
            if state.verification_result
            else {},
            "status": state.plan.status,
        }
        state.audit_records.append(record)

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
