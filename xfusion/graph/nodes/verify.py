from __future__ import annotations

from uuid import uuid4

from xfusion.domain.enums import (
    ApprovalMode,
    FailureClass,
    ReasoningRole,
    RiskTier,
    StepStatus,
    VerificationStatus,
)
from xfusion.domain.models.execution_plan import PlanStep
from xfusion.domain.models.verification import (
    RepairApprovalRequirement,
    RepairEquivalenceDecision,
    RepairProposal,
    RepairStepDraft,
    RepairTrigger,
    VerificationResult,
)
from xfusion.graph.roles import record_role_proposal
from xfusion.graph.state import AgentGraphState
from xfusion.policy.approval import stable_hash


def _no_tool_error(output: dict[str, object]) -> bool:
    return "error" not in output


def _has_any(output: dict[str, object], *keys: str) -> bool:
    return any(bool(output.get(key)) for key in keys)


def _verify_state_re_read(output: dict[str, object]) -> tuple[bool, str]:
    if not _no_tool_error(output):
        return False, "Tool output contained an error."
    if output:
        return True, "State was re-read and returned structured facts."
    return False, "State re-read returned no structured facts."


def _verify_port_process_recheck(
    step_parameters: dict[str, object],
    step_success_condition: str,
    output: dict[str, object],
) -> tuple[bool, str]:
    if not _no_tool_error(output):
        return False, "Port/process re-check returned an error."

    pids = output.get("pids")
    matches = output.get("matches")
    stdout = str(output.get("stdout", ""))
    condition = step_success_condition.lower()
    expect_free = (
        bool(step_parameters.get("expect_free")) or "free" in condition or "no pid" in condition
    )

    if expect_free:
        port_is_free = pids == [] or matches == [] or output.get("ok") is True
        return (
            port_is_free,
            "Port is free after re-check."
            if port_is_free
            else "Port still has matching process activity.",
        )

    has_result = (
        bool(pids) or bool(matches) or bool(stdout) or pids == [] or output.get("ok") is True
    )
    return (
        has_result,
        "Port/process state was re-read."
        if has_result
        else "Port/process state could not be re-read.",
    )


def _verify_filesystem_metadata(output: dict[str, object]) -> tuple[bool, str]:
    if not _no_tool_error(output):
        return False, "Filesystem metadata re-check returned an error."
    if (
        _has_any(output, "matches", "items", "previewed_candidates")
        or output.get("exists") is not None
    ):
        return True, "Filesystem metadata was returned in structured output."
    return False, "Filesystem metadata was missing from structured output."


def _verify_existence(step_success_condition: str, output: dict[str, object]) -> tuple[bool, str]:
    if not _no_tool_error(output):
        return False, "Existence check returned an error."

    condition = step_success_condition.lower()
    if "absent" in condition or "no longer exists" in condition:
        verified = output.get("absent") is True or output.get("exists") is False
        return (
            verified,
            "Target absence confirmed." if verified else "Target still appears to exist.",
        )

    verified = output.get("exists") is True or output.get("verified") is True
    return (
        verified,
        "Target existence confirmed." if verified else "Target existence was not confirmed.",
    )


def _verify_command_exit_plus_state(output: dict[str, object]) -> tuple[bool, str]:
    if not _no_tool_error(output):
        return False, "Command output contained an error."
    if _has_any(output, "processes", "pid", "stdout") or output.get("ok") is True:
        return True, "Command succeeded and returned structured state evidence."
    return False, "Command did not return structured state evidence."


def _dispatch_verification(
    method: str,
    step_success_condition: str,
    step_parameters: dict[str, object],
    output: dict[str, object],
) -> tuple[bool, str]:
    normalized = method.replace("-", "_")
    if normalized in {"state_read", "state_re_read"}:
        return _verify_state_re_read(output)
    if normalized in {"port_recheck", "port_process_recheck"}:
        return _verify_port_process_recheck(step_parameters, step_success_condition, output)
    if normalized in {"filesystem_metadata_recheck", "filesystem_metadata_re_read"}:
        return _verify_filesystem_metadata(output)
    if normalized in {"existence_check", "existence_nonexistence_check"}:
        return _verify_existence(step_success_condition, output)
    if normalized in {"command_exit_status_plus_state", "tool_success"}:
        return _verify_command_exit_plus_state(output)
    if normalized == "none":
        return True, "No verification required for non-executed/refusal-only step."
    return False, f"Unknown verification method: {method}"


def _verification_outcome(success: bool, summary: str) -> VerificationStatus:
    if success:
        return VerificationStatus.SUCCESS
    lowered = summary.lower()
    if "unknown verification method" in lowered or "could not" in lowered or "missing" in lowered:
        return VerificationStatus.INCONCLUSIVE
    return VerificationStatus.FAILED


def _build_repair_proposal(
    state: AgentGraphState,
    *,
    step: PlanStep,
    verification: VerificationResult,
) -> RepairProposal:
    proposal_id = f"repair_{uuid4().hex[:10]}"
    trigger = RepairTrigger(
        verification_id=verification.verification_id,
        failed_step_id=step.step_id,
        verification_method=verification.method,
        verification_outcome=verification.outcome,
        failure_class=step.failure_class or FailureClass.VERIFICATION_FAILURE.value,
        evidence_fingerprint=stable_hash(verification.details),
        summary=verification.summary,
    )
    normalized_args = dict(step.normalized_args or step.args)
    material_change_fields: list[str] = []
    escalation = False

    if step.capability == "process.kill" and normalized_args.get("signal") == "TERM":
        normalized_args["signal"] = "KILL"
        escalation = True
        material_change_fields.extend(["args.signal", "risk_tier"])
    elif verification.outcome == VerificationStatus.INCONCLUSIVE:
        material_change_fields.append("verification_outcome")

    proposed_step_id = f"{step.step_id}_repair_{len(state.repair_proposals) + 1}"
    draft = RepairStepDraft(
        proposed_step_id=proposed_step_id,
        capability=str(step.capability),
        args=normalized_args,
        depends_on=list(step.depends_on),
        justification=(
            "Escalate to stronger bounded action after failed verification."
            if escalation
            else (
                "Retry with typed deterministic repair path after failed/inconclusive verification."
            )
        ),
        verification_method=step.verification_method,
        success_condition=step.success_condition,
        failure_condition=step.failure_condition,
        fallback_action=step.fallback_action,
        escalation=escalation,
    )

    equivalent = (
        draft.capability == str(step.capability)
        and draft.args == (step.normalized_args or step.args)
        and not escalation
    )
    policy_allows_reuse = bool(
        state.plan
        and state.plan.approval_summary.get("allow_equivalent_repair_approval_reuse", False)
    )
    prior_approval_reusable = (
        equivalent
        and policy_allows_reuse
        and bool(step.approval_id)
        and step.approval_id in state.approval_records
    )
    equivalence = RepairEquivalenceDecision(
        equivalent=equivalent,
        material_change_fields=material_change_fields,
        policy_allows_equivalent_approval_reuse=policy_allows_reuse,
        prior_approval_reusable=prior_approval_reusable,
        reason=(
            "Equivalent repair proposal within identical capability and arguments."
            if equivalent
            else "Materially changed repair requires deterministic full re-entry."
        ),
    )
    approval_requirement = RepairApprovalRequirement(
        requires_reapproval=not prior_approval_reusable,
        required_mode=step.approval_mode if step.approval_mode else ApprovalMode.HUMAN,
        reason=(
            "Prior approval may be reused only because policy explicitly allows equivalent repair."
            if prior_approval_reusable
            else "Repair is materially changed or policy does not allow approval reuse."
        ),
    )
    return RepairProposal(
        proposal_id=proposal_id,
        proposed_by_role=ReasoningRole.VERIFICATION,
        trigger=trigger,
        original_step_id=step.step_id,
        draft=draft,
        equivalence=equivalence,
        approval_requirement=approval_requirement,
        prior_approval_id=step.approval_id,
        prior_risk_tier=step.risk_hint or RiskTier.TIER_1,
        audit_link=f"{verification.verification_id}:{step.step_id}",
        state="accepted_for_reentry",
        deterministic_reason="verification_failure_requires_typed_repair",
    )


def _append_repair_step(
    state: AgentGraphState,
    *,
    source_step: PlanStep,
    proposal: RepairProposal,
) -> None:
    if not state.plan:
        return
    if any(step.step_id == proposal.draft.proposed_step_id for step in state.plan.steps):
        return

    repair_step = PlanStep(
        id=proposal.draft.proposed_step_id,
        capability=proposal.draft.capability,
        args=proposal.draft.args,
        depends_on=proposal.draft.depends_on,
        expected_outputs=dict(source_step.expected_outputs),
        justification=proposal.draft.justification,
        risk_hint=RiskTier.TIER_2 if proposal.draft.escalation else source_step.risk_hint,
        approval_required_hint=source_step.approval_mode,
        preview_summary=(
            f"Repair for {source_step.step_id}: escalate TERM->KILL."
            if proposal.draft.escalation
            else f"Repair for {source_step.step_id}: retry under deterministic controls."
        ),
        on_failure=source_step.on_failure,
        verification_step_ids=(
            list(source_step.verification_step_ids)
            if source_step.verification_step_ids
            else [proposal.draft.proposed_step_id]
        ),
        verification_method=proposal.draft.verification_method,
        success_condition=proposal.draft.success_condition,
        failure_condition=proposal.draft.failure_condition,
        fallback_action=proposal.draft.fallback_action,
        repair_of_step_id=source_step.step_id,
        repair_proposal_id=proposal.proposal_id,
    )
    if proposal.equivalence.prior_approval_reusable and source_step.approval_id:
        repair_step.approval_id = source_step.approval_id
        repair_step.action_fingerprint = source_step.action_fingerprint
    state.plan.steps.append(repair_step)
    state.active_repair_step_ids.append(repair_step.step_id)


def verify_node(state: AgentGraphState) -> AgentGraphState:
    """Run mandatory post-action verification for the current step."""
    if not state.plan:
        return state

    if not state.current_step_id:
        step = state.plan.next_executable_step()
        if step:
            state.current_step_id = step.step_id

    if not state.current_step_id:
        return state

    step = next(
        (candidate for candidate in state.plan.steps if candidate.step_id == state.current_step_id),
        None,
    )
    if not step or step.status != StepStatus.RUNNING:
        return state

    tool_output = state.step_outputs.get(step.step_id, state.last_tool_output or {})
    success, summary = _dispatch_verification(
        step.verification_method,
        step.success_condition,
        step.normalized_args or step.args,
        tool_output,
    )

    outcome = _verification_outcome(success, summary)
    verification = VerificationResult(
        verification_id=f"ver_{uuid4().hex[:10]}",
        step_id=step.step_id,
        success=success,
        method=step.verification_method,
        summary=summary,
        outcome=outcome,
        failure_class=step.failure_class if not success else None,
        details=tool_output,
    )
    state.verification_result = verification
    record_role_proposal(
        state,
        role=ReasoningRole.VERIFICATION,
        proposal_type="verification_outcome",
        payload={
            "verification_id": verification.verification_id,
            "step_id": step.step_id,
            "outcome": verification.outcome.value,
            "summary": verification.summary,
        },
        deterministic_layer="verify_node",
        attributable_step_id=step.step_id,
        consumes_redacted_inputs_only=True,
    )

    if success:
        step.status = StepStatus.SUCCESS
    else:
        step.status = StepStatus.FAILED
        step.failure_class = FailureClass.VERIFICATION_FAILURE.value
        step.failure_details = {
            "failure_class": FailureClass.VERIFICATION_FAILURE.value,
            "method": step.verification_method,
            "summary": summary,
            "details": tool_output,
        }
        if step.repair_of_step_id:
            state.response = (
                f"Verification {verification.outcome.value}: {summary}. "
                "Repair execution failed; no automatic nested repair will be proposed."
            )
            return state
        if any(
            proposal.original_step_id == step.step_id and proposal.state == "accepted_for_reentry"
            for proposal in state.repair_proposals
        ):
            state.response = (
                f"Verification {verification.outcome.value}: {summary}. "
                "Repair already attempted for this failed step; escalation requires operator input."
            )
            return state
        repair = _build_repair_proposal(state, step=step, verification=verification)
        state.repair_proposals.append(repair)
        record_role_proposal(
            state,
            role=ReasoningRole.VERIFICATION,
            proposal_type="repair_proposal",
            payload={
                "proposal_id": repair.proposal_id,
                "original_step_id": repair.original_step_id,
                "capability": repair.draft.capability,
                "args": repair.draft.args,
                "equivalent": repair.equivalence.equivalent,
                "requires_reapproval": repair.approval_requirement.requires_reapproval,
                "auto_execute_repair": False,
            },
            deterministic_layer="verify_node",
            attributable_step_id=step.step_id,
            consumes_redacted_inputs_only=True,
        )
        _append_repair_step(state, source_step=step, proposal=repair)
        state.response = (
            f"Verification {verification.outcome.value}: {summary}. "
            f"Typed repair proposed ({repair.proposal_id}) and queued for deterministic re-entry."
        )

    return state
