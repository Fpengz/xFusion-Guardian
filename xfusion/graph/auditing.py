from __future__ import annotations

from datetime import datetime

from xfusion.audit.jsonl_sink import JsonlAuditSink
from xfusion.audit.logger import AuditLogger
from xfusion.domain.models.execution_plan import PlanStep
from xfusion.graph.state import AgentGraphState
from xfusion.security.redaction import redact_value


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
                "capability": step.capability,
                "normalized_args": step.normalized_args or step.args,
                "argument_provenance": step.argument_provenance,
                "resolved_references": step.resolved_references,
                "output": state.step_outputs.get(step.step_id, {}),
            }
        )
        if step.failure_details:
            action.update(step.failure_details)
    after_state: dict[str, object] = {
        "plan_status": state.plan.status,
        "step_status": step.status,
    }
    verification = verification_result or (
        state.verification_result.model_dump() if state.verification_result else {}
    )

    original_user_request, request_redaction = redact_value(state.user_input)
    interpreted_intent, intent_redaction = redact_value(state.plan.goal)
    role_proposals, role_redaction = redact_value(
        {key: contract.model_dump() for key, contract in state.role_contracts.items()}
    )
    plan_draft, plan_redaction = redact_value(state.plan.model_dump(mode="json"))
    normalized_args, args_redaction = redact_value(step.normalized_args or step.args)
    summary_value, summary_redaction = redact_value(summary)
    redacted_action, action_redaction = redact_value(action)
    redacted_verification, verification_redaction = redact_value(verification)
    normalized_output = state.step_outputs.get(step.step_id, {})
    redacted_output, output_redaction = redact_value(normalized_output)

    record = {
        "timestamp": datetime.now().isoformat(),
        "plan_id": state.plan.plan_id,
        "original_user_request": original_user_request,
        "interpreted_intent": interpreted_intent,
        "role_proposals": role_proposals,
        "plan_draft": plan_draft,
        "validation_result": state.validation_result.model_dump(mode="json")
        if state.validation_result
        else None,
        "step_id": step.step_id,
        "capability": step.capability,
        "normalized_args": normalized_args,
        "argument_provenance": step.argument_provenance,
        "resolved_references": step.resolved_references,
        "matched_policy_rule": step.policy_rule_id,
        "approval_mode": step.approval_mode,
        "approval_id": step.approval_id,
        "action_fingerprint": step.action_fingerprint,
        "adapter_id": step.adapter_id,
        "interaction_state": state.plan.interaction_state,
        "before_state": before_state,
        "action_taken": redacted_action,
        "after_state": after_state,
        "verification_result": redacted_verification,
        "normalized_output": redacted_output,
        "redaction_metadata": {
            "action": action_redaction,
            "verification": verification_redaction,
            "output": output_redaction,
            "original_user_request": request_redaction,
            "interpreted_intent": intent_redaction,
            "role_proposals": role_redaction,
            "plan_draft": plan_redaction,
            "normalized_args": args_redaction,
            "summary": summary_redaction,
            "step": step.redaction_metadata,
        },
        "status": status,
        "summary": summary_value,
    }
    state.audit_records.append(record)

    if state.audit_log_path:
        AuditLogger(JsonlAuditSink(state.audit_log_path)).log_step(
            plan_id=state.plan.plan_id,
            step_id=step.step_id,
            interaction_state=str(state.plan.interaction_state),
            before_state=before_state,
            action_taken=redacted_action,
            after_state=after_state,
            verification_result=redacted_verification,
            status=status,
            summary=str(summary_value),
        )
