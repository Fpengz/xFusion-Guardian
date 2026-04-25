from __future__ import annotations

from xfusion.capabilities.registry import build_default_capability_registry
from xfusion.domain.enums import InteractionState, PolicyDecisionValue, ReasoningRole, StepStatus
from xfusion.graph.auditing import log_graph_event
from xfusion.graph.roles import record_role_proposal
from xfusion.graph.state import AgentGraphState
from xfusion.planning.reference_resolver import resolve_args
from xfusion.policy.approval import (
    build_argument_provenance,
    build_step_binding,
    create_approval_record,
    stable_hash,
)
from xfusion.policy.envelope import build_action_integrity_hash
from xfusion.policy.rules import (
    build_policy_snapshot_hash,
    build_policy_snapshot_payload,
    evaluate_policy,
)


def policy_node(state: AgentGraphState) -> AgentGraphState:
    """Call deterministic policy rules for the next executable step."""
    if not state.plan:
        return state

    step = state.plan.next_executable_step()
    if not step or step.status == "running":
        return state

    state.current_step_id = step.step_id

    registry = build_default_capability_registry()
    capability = registry.require(str(step.capability))

    try:
        resolved_args = resolve_args(
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
        state.plan.interaction_state = InteractionState.FAILED
        state.plan.status = "failed"
        state.response = f"Reference resolution failed: {e}"
        log_graph_event(
            state,
            step=step,
            status="reference_resolution_failed",
            summary=state.response,
            action_taken={"capability": step.capability, "args": step.args, "error": str(e)},
        )
        return state

    provenance = build_argument_provenance(step.args)
    step.normalized_args = resolved_args
    step.argument_provenance = provenance
    step.adapter_id = capability.adapter_id

    decision = evaluate_policy(
        capability_name=str(step.capability),
        resolved_args=resolved_args,
        argument_provenance=provenance,
        environment=state.environment,
        actor_type="assistant",
        host_class="production",
        target_scope="explicit",
        request_intent=state.plan.intent_class,
        prior_approval_state={
            approval_id: approval.model_dump(mode="json")
            for approval_id, approval in state.approval_records.items()
        },
    )

    state.policy_decision = decision
    record_role_proposal(
        state,
        role=ReasoningRole.SUPERVISOR,
        proposal_type="coordination",
        payload={
            "step_id": step.step_id,
            "policy_decision": decision.decision.value,
            "risk_tier": decision.risk_tier.value,
            "approval_mode": decision.approval_mode.value,
        },
        deterministic_layer="policy_node",
        attributable_step_id=step.step_id,
        consumes_redacted_inputs_only=True,
    )

    step.risk_level = decision.risk_level
    step.policy_category = decision.policy_category
    step.final_risk_category = decision.policy_category
    step.requires_confirmation = decision.requires_approval
    step.policy_rule_id = decision.matched_rule_id
    step.approval_mode = decision.approval_mode
    step.risk_contract = decision.risk_contract.model_dump() if decision.risk_contract else {}
    step_binding = build_step_binding(state.plan, step)
    policy_snapshot = build_policy_snapshot_payload(
        capability_name=str(step.capability),
        normalized_args=resolved_args,
        argument_provenance=provenance,
        decision=decision,
        environment=state.environment,
        step_binding=step_binding,
    )
    step.policy_snapshot = policy_snapshot
    step.policy_snapshot_hash = build_policy_snapshot_hash(policy_snapshot)
    step.intent_hash = stable_hash(
        {"goal": state.plan.goal, "intent_class": state.plan.intent_class}
    )
    step.planned_action_hash = build_action_integrity_hash(step, resolved_args=resolved_args)
    step.non_execution_code = None
    step.non_execution_reason_text = None

    if decision.decision == PolicyDecisionValue.DENY:
        step.status = StepStatus.REFUSED
        step.failure_class = (
            "scope_violation"
            if {"scope_violation", "scope_not_explicit"} & set(decision.reason_codes)
            else "policy_denial"
        )
        step.non_execution_code = decision.deny_code or step.failure_class
        step.non_execution_reason_text = decision.reason_text
        step.failure_details = {
            "failure_class": step.failure_class,
            "non_execution_code": step.non_execution_code,
            "non_execution_reason_text": step.non_execution_reason_text,
            "policy_decision": decision.model_dump(),
        }
        state.plan.interaction_state = InteractionState.REFUSED
        state.plan.status = "refused"
        state.response = f"I cannot execute this step: {decision.reason_text}"
        log_graph_event(
            state,
            step=step,
            status=step.failure_class,
            summary=state.response,
            action_taken={
                "capability": step.capability,
                "normalized_args": resolved_args,
                "argument_provenance": provenance,
                "failure_class": step.failure_class,
                "policy_decision": decision.model_dump(),
            },
        )
    elif decision.decision == PolicyDecisionValue.REQUIRE_CONFIRMATION:
        step.confirmation_supplied = False
        existing = state.approval_records.get(step.approval_id or "")
        if existing and existing.is_approved:
            state.response = "Existing approval record found; validating before execution."
            return state

        approval = create_approval_record(
            plan=state.plan,
            step=step,
            capability=capability,
            normalized_args=resolved_args,
            target_context=state.plan.target_context,
            approval_mode=decision.approval_mode,
            risk_tier=decision.risk_tier,
            policy_snapshot_hash=step.policy_snapshot_hash or "",
            step_binding=step_binding,
            authorized_outputs=state.authorized_step_outputs,
        )
        state.approval_records[approval.approval_id] = approval
        state.pending_approval_id = approval.approval_id
        step.approval_id = approval.approval_id
        step.action_fingerprint = approval.action_fingerprint
        step.approved_action_hash = step.planned_action_hash

        state.plan.interaction_state = InteractionState.AWAITING_CONFIRMATION
        state.plan.status = "awaiting_confirmation"
        phrase = approval.typed_confirmation_phrase
        step.confirmation_phrase = phrase
        state.pending_confirmation_phrase = phrase
        confirmation_label = (
            "admin confirmation" if decision.confirmation_type == "admin" else "user confirmation"
        )
        state.response = (
            f"This action requires {confirmation_label}. "
            f"Preview: {approval.preview.action_summary}; impacted target: "
            f"{approval.preview.impacted_target}. Please type: '{phrase}'"
        )
        log_graph_event(
            state,
            step=step,
            status="approval_requested",
            summary=state.response,
            action_taken={
                "capability": step.capability,
                "normalized_args": resolved_args,
                "argument_provenance": provenance,
                "policy_decision": decision.model_dump(),
                "approval_request": approval.model_dump(mode="json"),
            },
        )

    return state
