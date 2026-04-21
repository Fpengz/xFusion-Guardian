from __future__ import annotations

from xfusion.domain.enums import InteractionState
from xfusion.graph.state import AgentGraphState
from xfusion.policy.rules import evaluate_policy


def policy_node(state: AgentGraphState) -> AgentGraphState:
    """Call deterministic policy rules for the next executable step."""
    if not state.plan:
        return state

    step = state.plan.next_executable_step()
    if not step or step.status == "running":
        return state

    state.current_step_id = step.step_id

    decision = evaluate_policy(
        tool=step.tool, parameters=step.parameters, environment=state.environment
    )

    state.policy_decision = decision

    # Update step with policy details
    step.risk_level = decision.risk_level
    step.requires_confirmation = decision.requires_confirmation

    if not decision.allowed:
        state.plan.interaction_state = InteractionState.REFUSED
        state.response = f"I cannot execute this step: {decision.reason}"
    elif decision.requires_confirmation:
        state.plan.interaction_state = InteractionState.AWAITING_CONFIRMATION
        # Requirements: Exact typed confirmation phrase is required.
        # Format: "I understand the risks of <intent>"
        phrase = f"I understand the risks of {step.intent}"
        step.confirmation_phrase = phrase
        state.pending_confirmation_phrase = phrase
        state.response = f"This action requires confirmation. Please type: '{phrase}'"

    return state
