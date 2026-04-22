from __future__ import annotations

from datetime import datetime

from xfusion.audit.jsonl_sink import JsonlAuditSink
from xfusion.audit.logger import AuditLogger
from xfusion.domain.models.execution_plan import PlanStep
from xfusion.graph.state import AgentGraphState


def log_graph_event(
    state: AgentGraphState,
    *,
    step: PlanStep,
    status: str,
    summary: str,
    action_taken: dict[str, object] | None = None,
    verification_result: dict[str, object] | None = None,
) -> None:
    """Append an in-memory and optional JSONL audit event."""
    if not state.plan:
        return

    before_state = state.environment.model_dump()
    if action_taken is not None:
        action = action_taken
    else:
        action = dict[str, object](
            {
                "tool": step.tool,
                "parameters": step.parameters,
                "output": state.step_outputs.get(step.step_id, {}),
            }
        )
    after_state: dict[str, object] = {
        "plan_status": state.plan.status,
        "step_status": step.status,
    }
    verification = verification_result or (
        state.verification_result.model_dump() if state.verification_result else {}
    )

    record = {
        "timestamp": datetime.now().isoformat(),
        "plan_id": state.plan.plan_id,
        "step_id": step.step_id,
        "interaction_state": state.plan.interaction_state,
        "before_state": before_state,
        "action_taken": action,
        "after_state": after_state,
        "verification_result": verification,
        "status": status,
        "summary": summary,
    }
    state.audit_records.append(record)

    if state.audit_log_path:
        AuditLogger(JsonlAuditSink(state.audit_log_path)).log_step(
            plan_id=state.plan.plan_id,
            step_id=step.step_id,
            interaction_state=str(state.plan.interaction_state),
            before_state=before_state,
            action_taken=action,
            after_state=after_state,
            verification_result=verification,
            status=status,
            summary=summary,
        )
