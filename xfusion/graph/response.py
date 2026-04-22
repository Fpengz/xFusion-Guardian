from __future__ import annotations

from xfusion.domain.enums import InteractionState
from xfusion.graph.state import AgentGraphState


def format_agent_response(state: AgentGraphState) -> str:
    """Build the judge-facing response contract from deterministic state."""
    if not state.plan:
        return state.response

    plan = state.plan
    env = state.environment
    plan_tools = ", ".join(step.tool for step in plan.steps) if plan.steps else "none"
    risk = state.policy_decision.risk_level if state.policy_decision else "none"
    risk_reason = (
        state.policy_decision.reason if state.policy_decision else "No policy action needed."
    )
    verification = (
        state.verification_result.summary
        if state.verification_result
        else "Not executed for this state."
    )
    action = state.response or "No action executed."

    if plan.interaction_state == InteractionState.AWAITING_CONFIRMATION:
        action = f"Confirmation required: type '{state.pending_confirmation_phrase}'."
    elif plan.interaction_state == InteractionState.AWAITING_DISAMBIGUATION:
        action = plan.clarification_question or state.response

    next_step = _next_recommendation(state)

    return "\n".join(
        [
            f"Intent: {plan.goal}",
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
            f"State: {plan.interaction_state}; status={plan.status}",
            f"Next: {next_step}",
        ]
    )


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
