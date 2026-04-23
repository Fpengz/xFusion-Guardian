from __future__ import annotations

from xfusion.capabilities.registry import build_default_capability_registry
from xfusion.domain.enums import InteractionState, PolicyDecisionValue, StepStatus
from xfusion.execution.runtime import ControlledAdapterRuntime
from xfusion.graph.state import AgentGraphState
from xfusion.planning.reference_resolver import resolve_args
from xfusion.policy.approval import (
    build_argument_provenance,
    build_referenced_output_fingerprints,
    build_step_binding,
    validate_approval_for_invocation,
)
from xfusion.policy.rules import (
    build_policy_snapshot_hash,
    build_policy_snapshot_payload,
    evaluate_policy,
)


def _fail_non_execution(
    state: AgentGraphState,
    *,
    step,
    status: StepStatus,
    failure_class: str,
    code: str,
    reason_text: str,
    details: dict[str, object] | None = None,
) -> AgentGraphState:
    step.status = status
    step.failure_class = failure_class
    step.non_execution_code = code
    step.non_execution_reason_text = reason_text
    step.failure_details = {
        "failure_class": failure_class,
        "non_execution_code": code,
        "non_execution_reason_text": reason_text,
        **(details or {}),
    }
    state.response = reason_text
    return state


def execute_node(state: AgentGraphState, registry=None) -> AgentGraphState:
    """Call only registered typed tools with resolved parameters."""
    if not state.plan or state.plan.interaction_state != InteractionState.EXECUTING:
        return state

    step = state.plan.next_executable_step()
    if not step:
        return state

    state.current_step_id = step.step_id

    if not registry:
        # This is a fallback for testing, registry should be injected
        state.response = "Internal Error: Tool registry not initialized."
        return state

    step.status = StepStatus.RUNNING
    step.failure_class = None
    step.non_execution_code = None
    step.non_execution_reason_text = None
    step.failure_details = {}
    step.authorized_output_accepted = False
    step.command_trace = []
    state.step_outputs.pop(step.step_id, None)
    state.authorized_step_outputs.pop(step.step_id, None)
    state.last_tool_output = None
    state.verification_result = None

    capability = build_default_capability_registry().require(str(step.capability))

    try:
        resolved_params = resolve_args(
            step.args,
            plan=state.plan,
            authorized_outputs=state.authorized_step_outputs,
        )
    except ValueError as e:
        return _fail_non_execution(
            state,
            step=step,
            status=StepStatus.FAILED,
            failure_class="reference_resolution_failed",
            code="reference_resolution_failed",
            reason_text=f"Parameter resolution failed: {e}",
            details={
                "capability": step.capability,
                "args": step.args,
                "error": str(e),
            },
        )

    provenance = build_argument_provenance(step.args)
    step_binding = build_step_binding(state.plan, step)

    policy_recheck = evaluate_policy(
        capability_name=str(step.capability),
        resolved_args=resolved_params,
        argument_provenance=provenance,
        environment=state.environment,
        actor_type="assistant",
        host_class="production",
        target_scope="explicit",
        request_intent=state.plan.intent_class,
        prior_approval_state={
            approval_id: record.model_dump(mode="json")
            for approval_id, record in state.approval_records.items()
        },
    )
    state.policy_decision = policy_recheck
    live_policy_snapshot = build_policy_snapshot_payload(
        capability_name=str(step.capability),
        normalized_args=resolved_params,
        argument_provenance=provenance,
        decision=policy_recheck,
        environment=state.environment,
        step_binding=step_binding,
    )
    live_policy_snapshot_hash = build_policy_snapshot_hash(live_policy_snapshot)

    if step.policy_snapshot_hash and step.policy_snapshot_hash != live_policy_snapshot_hash:
        return _fail_non_execution(
            state,
            step=step,
            status=StepStatus.FAILED,
            failure_class="approval_invalidated",
            code="policy_integrity_mismatch",
            reason_text=(
                "Execution blocked: policy integrity check failed due to stale or changed state."
            ),
            details={
                "stored_policy_snapshot_hash": step.policy_snapshot_hash,
                "live_policy_snapshot_hash": live_policy_snapshot_hash,
                "policy_decision": policy_recheck.model_dump(),
            },
        )

    step.policy_snapshot = live_policy_snapshot
    step.policy_snapshot_hash = live_policy_snapshot_hash
    step.policy_rule_id = policy_recheck.matched_rule_id
    step.approval_mode = policy_recheck.approval_mode
    step.risk_level = policy_recheck.risk_level
    step.risk_contract = (
        policy_recheck.risk_contract.model_dump() if policy_recheck.risk_contract else {}
    )
    step.requires_confirmation = policy_recheck.requires_approval

    if policy_recheck.decision == PolicyDecisionValue.DENY:
        state.plan.interaction_state = InteractionState.REFUSED
        state.plan.status = "refused"
        return _fail_non_execution(
            state,
            step=step,
            status=StepStatus.REFUSED,
            failure_class="policy_denial",
            code=policy_recheck.deny_code or "policy_denial",
            reason_text=f"Step execution blocked by policy: {policy_recheck.reason_text}",
            details={"policy_decision": policy_recheck.model_dump()},
        )

    if policy_recheck.decision == PolicyDecisionValue.REQUIRE_CONFIRMATION and not step.approval_id:
        return _fail_non_execution(
            state,
            step=step,
            status=StepStatus.FAILED,
            failure_class="approval_missing",
            code="confirmation_required_without_approval",
            reason_text="Step execution blocked: explicit confirmation is required first.",
            details={"policy_decision": policy_recheck.model_dump()},
        )

    if step.approval_id:
        approval = state.approval_records.get(step.approval_id)
        if approval is None:
            return _fail_non_execution(
                state,
                step=step,
                status=StepStatus.FAILED,
                failure_class="approval_missing",
                code="approval_record_missing",
                reason_text="Approval required but no approval record exists.",
                details={
                    "approval_id": step.approval_id,
                    "capability": step.capability,
                },
            )
        if policy_recheck.decision != PolicyDecisionValue.REQUIRE_CONFIRMATION:
            return _fail_non_execution(
                state,
                step=step,
                status=StepStatus.FAILED,
                failure_class="approval_invalidated",
                code="policy_decision_changed",
                reason_text=(
                    "Approval invalidated before execution: policy decision changed after approval."
                ),
                details={
                    "approval_id": approval.approval_id,
                    "capability": step.capability,
                    "normalized_args": resolved_params,
                    "policy_decision": policy_recheck.model_dump(),
                },
            )
        is_valid, reason = validate_approval_for_invocation(
            approval=approval,
            capability=capability,
            normalized_args=resolved_params,
            target_context=state.plan.target_context,
            approval_mode=approval.approval_mode,
            risk_tier=approval.risk_tier,
            risk_contract=step.risk_contract,
            policy_snapshot_hash=live_policy_snapshot_hash,
            step_binding=step_binding,
            argument_provenance=provenance,
            referenced_output_fingerprints=build_referenced_output_fingerprints(
                step.args, state.authorized_step_outputs
            ),
        )
        if not is_valid:
            return _fail_non_execution(
                state,
                step=step,
                status=StepStatus.FAILED,
                failure_class="approval_invalidated",
                code=reason,
                reason_text=f"Approval invalidated before execution: {reason}",
                details={
                    "reason": reason,
                    "approval_id": approval.approval_id,
                    "capability": step.capability,
                    "normalized_args": resolved_params,
                },
            )
    elif step.requires_confirmation:
        return _fail_non_execution(
            state,
            step=step,
            status=StepStatus.FAILED,
            failure_class="approval_missing",
            code="requires_confirmation_without_approval_record",
            reason_text="Approval required but no approval record exists.",
            details={
                "capability": step.capability,
                "step_id": step.step_id,
            },
        )

    outcome = ControlledAdapterRuntime(registry).execute(
        capability=capability,
        normalized_args=resolved_params,
    )
    trace = getattr(registry, "last_execution_trace", [])
    step.command_trace = trace if isinstance(trace, list) else []

    step.normalized_args = resolved_params
    step.adapter_id = capability.adapter_id
    step.redaction_metadata = outcome.redaction_metadata
    step.started_at = outcome.invocation.started_at.isoformat()
    step.ended_at = outcome.ended_at.isoformat()

    if outcome.status != "succeeded" or "error" in outcome.normalized_output:
        step.status = StepStatus.FAILED
        step.failure_class = outcome.status
        step.non_execution_code = outcome.status
        step.non_execution_reason_text = outcome.summary
        step.failure_details = outcome.normalized_output
        state.last_tool_output = None
        state.response = f"Step failed: {outcome.summary}"
    else:
        state.last_tool_output = outcome.normalized_output
        state.step_outputs[step.step_id] = outcome.normalized_output
        state.response = outcome.summary

    return state
