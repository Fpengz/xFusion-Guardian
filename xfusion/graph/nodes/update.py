from __future__ import annotations

from datetime import datetime

from xfusion.audit.jsonl_sink import JsonlAuditSink
from xfusion.audit.logger import AuditLogger
from xfusion.domain.enums import InteractionState, StepStatus
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
        action_taken: dict[str, object] = {
            "tool": step.tool if step else None,
            "parameters": step.parameters if step else {},
            "output": state.step_outputs.get(state.current_step_id, {}),
        }
        after_state: dict[str, object] = {
            "plan_status": state.plan.status,
            "step_status": step.status if step else "unknown",
        }
        record = {
            "timestamp": datetime.now().isoformat(),
            "plan_id": state.plan.plan_id,
            "step_id": state.current_step_id,
            "interaction_state": state.plan.interaction_state,
            "before_state": state.environment.model_dump(),
            "action_taken": action_taken,
            "after_state": after_state,
            "verification_result": state.verification_result.model_dump()
            if state.verification_result
            else {},
            "status": str(step.status if step else state.plan.status),
            "summary": state.response,
        }
        state.audit_records.append(record)
        if state.audit_log_path and step:
            AuditLogger(JsonlAuditSink(state.audit_log_path)).log_step(
                plan_id=state.plan.plan_id,
                step_id=state.current_step_id,
                interaction_state=str(state.plan.interaction_state),
                before_state=record["before_state"],
                action_taken=action_taken,
                after_state=after_state,
                verification_result=record["verification_result"],
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
