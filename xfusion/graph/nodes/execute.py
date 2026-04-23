from __future__ import annotations

from xfusion.capabilities.registry import build_default_capability_registry
from xfusion.domain.enums import InteractionState, PolicyDecisionValue, StepStatus
from xfusion.execution.runtime import ControlledAdapterRuntime
from xfusion.graph.state import AgentGraphState
from xfusion.planning.reference_resolver import resolve_args
from xfusion.policy.approval import (
    build_argument_provenance,
    build_referenced_output_fingerprints,
    validate_approval_for_invocation,
)
from xfusion.policy.rules import evaluate_policy


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
    step.failure_details = {}
    step.authorized_output_accepted = False
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
        step.status = StepStatus.FAILED
        step.failure_class = "reference_resolution_failed"
        step.failure_details = {
            "failure_class": "reference_resolution_failed",
            "capability": step.capability,
            "args": step.args,
            "error": str(e),
        }
        state.response = f"Parameter resolution failed: {e}"
        return state

    if step.approval_id:
        approval = state.approval_records.get(step.approval_id)
        if approval is None:
            step.status = StepStatus.FAILED
            step.failure_class = "approval_missing"
            step.failure_details = {
                "failure_class": "approval_missing",
                "approval_id": step.approval_id,
                "capability": step.capability,
            }
            state.response = "Approval required but no approval record exists."
            return state
        is_valid, reason = validate_approval_for_invocation(
            approval=approval,
            capability=capability,
            normalized_args=resolved_params,
            target_context=state.plan.target_context,
            approval_mode=approval.approval_mode,
            risk_tier=approval.risk_tier,
            argument_provenance=build_argument_provenance(step.args),
            referenced_output_fingerprints=build_referenced_output_fingerprints(
                step.args, state.authorized_step_outputs
            ),
        )
        if not is_valid:
            step.status = StepStatus.FAILED
            step.failure_class = (
                "approval_invalidated"
                if reason in {"action_fingerprint_mismatch", "material_change"}
                else reason
            )
            step.failure_details = {
                "failure_class": step.failure_class,
                "reason": reason,
                "approval_id": approval.approval_id,
                "capability": step.capability,
                "normalized_args": resolved_params,
            }
            state.response = f"Approval invalidated before execution: {reason}"
            return state

        policy_recheck = evaluate_policy(
            capability_name=str(step.capability),
            resolved_args=resolved_params,
            argument_provenance=build_argument_provenance(step.args),
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
        if policy_recheck.decision != PolicyDecisionValue.REQUIRE_APPROVAL:
            step.status = StepStatus.FAILED
            step.failure_class = "approval_invalidated"
            step.failure_details = {
                "failure_class": "approval_invalidated",
                "reason": "policy_decision_changed",
                "approval_id": approval.approval_id,
                "capability": step.capability,
                "normalized_args": resolved_params,
                "policy_decision": policy_recheck.model_dump(),
            }
            state.response = (
                "Approval invalidated before execution: policy decision changed after approval."
            )
            return state

    outcome = ControlledAdapterRuntime(registry).execute(
        capability=capability,
        normalized_args=resolved_params,
    )

    step.normalized_args = resolved_params
    step.adapter_id = capability.adapter_id
    step.redaction_metadata = outcome.redaction_metadata
    step.started_at = outcome.invocation.started_at.isoformat()
    step.ended_at = outcome.ended_at.isoformat()

    if outcome.status != "succeeded" or "error" in outcome.normalized_output:
        step.status = StepStatus.FAILED
        step.failure_class = outcome.status
        step.failure_details = outcome.normalized_output
        state.last_tool_output = None
        state.response = f"Step failed: {outcome.summary}"
    else:
        state.last_tool_output = outcome.normalized_output
        state.step_outputs[step.step_id] = outcome.normalized_output
        state.response = outcome.summary

    return state
