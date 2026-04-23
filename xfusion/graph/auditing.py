from __future__ import annotations

from datetime import datetime

from xfusion.audit.jsonl_sink import JsonlAuditSink
from xfusion.audit.logger import AuditLogger
from xfusion.domain.enums import ApprovalMode
from xfusion.domain.models.execution_plan import PlanStep
from xfusion.graph.state import AgentGraphState
from xfusion.security.redaction import redact_value


def _safe_redact(value: object) -> tuple[object, dict[str, object]]:
    try:
        redacted, meta = redact_value(value)
        return redacted, dict(meta)
    except Exception:  # noqa: BLE001 - auditing must fail closed without raw exposure.
        return (
            {"error": "redaction_failed_raw_value_withheld"},
            {"redacted": True, "counts": {}, "redaction_failed": True},
        )


def log_graph_event(
    state: AgentGraphState,
    *,
    step: PlanStep,
    status: str,
    summary: str,
    action_taken: dict[str, object] | None = None,
    verification_result: dict[str, object] | None = None,
) -> None:
    """Append an in-memory and optional JSONL audit event.

    All recorded fields are redacted before general-purpose exposure surfaces.
    """
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
                "command_trace": step.command_trace,
                "repair_of_step_id": step.repair_of_step_id,
                "repair_proposal_id": step.repair_proposal_id,
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

    original_user_request, request_redaction = _safe_redact(state.user_input)
    interpreted_intent, intent_redaction = _safe_redact(state.plan.goal)
    role_contracts, role_contracts_redaction = _safe_redact(
        {key: contract.model_dump() for key, contract in state.role_contracts.items()}
    )
    role_runtime_records, role_runtime_redaction = _safe_redact(
        [record.model_dump(mode="json") for record in state.role_runtime_records]
    )
    repair_proposals, repair_redaction = _safe_redact(
        [proposal.model_dump(mode="json") for proposal in state.repair_proposals]
    )
    plan_draft, plan_redaction = _safe_redact(state.plan.model_dump(mode="json"))
    normalized_args, args_redaction = _safe_redact(step.normalized_args or step.args)
    summary_value, summary_redaction = _safe_redact(summary)
    redacted_action, action_redaction = _safe_redact(action)
    redacted_verification, verification_redaction = _safe_redact(verification)
    normalized_output = state.step_outputs.get(step.step_id, {})
    redacted_output, output_redaction = _safe_redact(normalized_output)
    risk_contract, risk_contract_redaction = _safe_redact(step.risk_contract)
    policy_decision, policy_decision_redaction = _safe_redact(
        state.policy_decision.model_dump(mode="json") if state.policy_decision else {}
    )
    approval = state.approval_records.get(step.approval_id or "")
    confirmation_required = bool(
        step.requires_confirmation or step.approval_mode in {ApprovalMode.HUMAN, ApprovalMode.ADMIN}
    )
    confirmation_supplied = bool(approval and approval.is_approved)
    normalized_step = {
        "step_id": step.step_id,
        "capability": step.capability,
        "normalized_args": step.normalized_args or step.args,
    }

    record = {
        "timestamp": datetime.now().isoformat(),
        "plan_id": state.plan.plan_id,
        "original_user_request": original_user_request,
        "interpreted_intent": interpreted_intent,
        "role_contracts": role_contracts,
        "role_runtime_records": role_runtime_records,
        "plan_draft": plan_draft,
        "validation_result": state.validation_result.model_dump(mode="json")
        if state.validation_result
        else None,
        "normalized_step": normalized_step,
        "step_id": step.step_id,
        "capability": step.capability,
        "risk_classification": risk_contract,
        "policy_decision": policy_decision,
        "policy_decision_code": state.policy_decision.decision.value
        if state.policy_decision
        else None,
        "confirmation_type": (
            state.policy_decision.confirmation_type if state.policy_decision else "none"
        ),
        "deny_code": state.policy_decision.deny_code if state.policy_decision else None,
        "confirmation_required": confirmation_required,
        "confirmation_supplied": confirmation_supplied,
        "normalized_args": normalized_args,
        "argument_provenance": step.argument_provenance,
        "resolved_references": step.resolved_references,
        "repair_of_step_id": step.repair_of_step_id,
        "repair_proposal_id": step.repair_proposal_id,
        "matched_policy_rule": step.policy_rule_id,
        "approval_mode": step.approval_mode,
        "approval_id": step.approval_id,
        "action_fingerprint": step.action_fingerprint,
        "adapter_id": step.adapter_id,
        "step_started_at": step.started_at,
        "step_ended_at": step.ended_at,
        "interaction_state": state.plan.interaction_state,
        "before_state": before_state,
        "action_taken": redacted_action,
        "after_state": after_state,
        "verification_result": redacted_verification,
        "repair_proposals": repair_proposals,
        "normalized_output": redacted_output,
        "non_execution_reason": step.failure_class if step.status != "success" else None,
        "non_execution": (
            {
                "code": step.non_execution_code or step.failure_class,
                "reason_text": step.non_execution_reason_text,
            }
            if step.status != "success"
            else None
        ),
        "redaction_metadata": {
            "action": action_redaction,
            "verification": verification_redaction,
            "output": output_redaction,
            "risk_classification": risk_contract_redaction,
            "policy_decision": policy_decision_redaction,
            "original_user_request": request_redaction,
            "interpreted_intent": intent_redaction,
            "role_contracts": role_contracts_redaction,
            "role_runtime_records": role_runtime_redaction,
            "plan_draft": plan_redaction,
            "normalized_args": args_redaction,
            "summary": summary_redaction,
            "step": step.redaction_metadata,
            "repair_proposals": repair_redaction,
        },
        "status": status,
        "summary": summary_value,
    }
    state.audit_records.append(record)

    if state.audit_log_path:
        started = datetime.fromisoformat(step.started_at) if step.started_at else None
        ended = datetime.fromisoformat(step.ended_at) if step.ended_at else None
        action_for_log: dict[str, object]
        verification_for_log: dict[str, object]
        if isinstance(redacted_action, dict):
            action_for_log = {str(key): value for key, value in redacted_action.items()}
        else:
            action_for_log = {"value": redacted_action}
        if isinstance(redacted_verification, dict):
            verification_for_log = {str(key): value for key, value in redacted_verification.items()}
        else:
            verification_for_log = {"value": redacted_verification}
        AuditLogger(JsonlAuditSink(state.audit_log_path)).log_step(
            plan_id=state.plan.plan_id,
            step_id=step.step_id,
            interaction_state=str(state.plan.interaction_state),
            before_state=before_state,
            action_taken=action_for_log,
            after_state=after_state,
            verification_result=verification_for_log,
            step_started_at=started,
            step_ended_at=ended,
            status=status,
            summary=str(summary_value),
        )
