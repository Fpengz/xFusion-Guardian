from __future__ import annotations

from typing import Any, cast

from xfusion.domain.enums import InteractionState
from xfusion.graph.state import AgentGraphState


def format_agent_response(state: AgentGraphState) -> str:
    """Build the judge-facing response from authoritative audited state."""
    if not state.plan:
        return state.response

    plan = state.plan
    env = state.environment
    source_record = _latest_authoritative_record(state)
    source_plan = source_record.get("plan_draft") if source_record else None
    source_plan_dict = cast(dict[str, Any], source_plan) if isinstance(source_plan, dict) else {}
    source_steps = source_plan_dict.get("steps", [])
    plan_tools = _plan_tools_from_audit(source_steps) or (
        ", ".join(str(step.capability) for step in plan.steps) if plan.steps else "none"
    )
    policy_record = _policy_record_from_audit(source_record)
    risk = policy_record.get("risk_tier", "none")
    risk_reason = policy_record.get("reason", "No policy action needed.")
    verification_record = cast(
        dict[str, Any], source_record.get("verification_result", {}) if source_record else {}
    )
    verification = (
        verification_record.get("summary")
        if isinstance(verification_record, dict) and verification_record.get("summary")
        else "Not executed for this state."
    )
    action = (
        str(source_record.get("summary"))
        if source_record and source_record.get("summary")
        else state.response or "No action executed."
    )

    if plan.interaction_state == InteractionState.AWAITING_CONFIRMATION:
        action = f"Confirmation required: type '{state.pending_confirmation_phrase}'."
    elif plan.interaction_state == InteractionState.AWAITING_DISAMBIGUATION:
        action = plan.clarification_question or state.response

    next_step = _next_recommendation(state)
    audit_status = source_record["status"] if source_record else "not_recorded"
    intent = (
        str(source_record.get("interpreted_intent"))
        if source_record and source_record.get("interpreted_intent")
        else plan.goal
    )

    response = "\n".join(
        [
            f"Intent: {intent}",
            (
                "Environment: "
                f"{env.distro_family} {env.distro_version}; "
                f"user={env.current_user}; sudo={env.sudo_available}; "
                f"systemd={env.systemd_available}; package={env.package_manager}; "
                f"disk_pressure={env.disk_pressure}"
            ),
            f"Plan: {len(plan.steps)} step(s): {plan_tools}",
            f"Risk: {risk} - {risk_reason}",
            f"Action: {action}",
            f"Verification: {verification}",
            f"Audit: explanation derived from authoritative audit status={audit_status}",
            f"State: {plan.interaction_state}; status={plan.status}",
            f"Next: {next_step}",
        ]
    )
    state.audit_records.append(
        {
            "timestamp": "final",
            "plan_id": plan.plan_id,
            "event": "final_explanation_snapshot",
            "response": response,
            "source_audit_status": audit_status,
            "source_audit_record": source_record,
        }
    )
    return response


def _latest_authoritative_record(state: AgentGraphState) -> dict[str, object] | None:
    for record in reversed(state.audit_records):
        if not isinstance(record, dict):
            continue
        if record.get("event") == "final_explanation_snapshot":
            continue
        if record.get("status"):
            return record
    return None


def _plan_tools_from_audit(source_steps: object) -> str:
    if not isinstance(source_steps, list):
        return ""
    capabilities = [
        str(cast(dict[str, Any], step).get("capability"))
        for step in source_steps
        if isinstance(step, dict) and cast(dict[str, Any], step).get("capability")
    ]
    return ", ".join(capabilities)


def _policy_record_from_audit(source_record: dict[str, object] | None) -> dict[str, object]:
    if not source_record:
        return {}
    action = source_record.get("action_taken")
    if not isinstance(action, dict):
        return {}
    action_dict = cast(dict[str, Any], action)
    policy_decision = action_dict.get("policy_decision")
    if isinstance(policy_decision, dict):
        return policy_decision
    return {}


def _next_recommendation(state: AgentGraphState) -> str:
    plan = state.plan
    if not plan:
        return "Ask for a Linux administration task."
    if plan.interaction_state == InteractionState.AWAITING_CONFIRMATION:
        return "Type the exact confirmation phrase to proceed, or anything else to abort."
    if plan.interaction_state == InteractionState.AWAITING_DISAMBIGUATION:
        return "Provide the missing target, scope, or risk boundary."
    if plan.interaction_state == InteractionState.REFUSED:
        return "Choose a narrower safe target or request a read-only inspection."
    if plan.interaction_state == InteractionState.FAILED:
        return "Review the verification failure before retrying."
    if plan.interaction_state == InteractionState.COMPLETED:
        if "disk" in plan.goal.lower() and (
            "clean" in plan.goal.lower() or "full" in plan.goal.lower()
        ):
            return "Consider preventive monitoring for disk pressure and cleanup candidate growth."
        return "Review the verification result and audit log before taking follow-up action."
    return "Continue with the next safe planned step."
