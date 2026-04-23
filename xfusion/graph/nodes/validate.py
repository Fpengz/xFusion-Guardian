from __future__ import annotations

from xfusion.capabilities.registry import build_default_capability_registry
from xfusion.domain.enums import InteractionState, ReasoningRole
from xfusion.graph.auditing import log_graph_event
from xfusion.graph.roles import record_role_proposal
from xfusion.graph.state import AgentGraphState
from xfusion.planning.validator import validate_plan


def validate_node(state: AgentGraphState) -> AgentGraphState:
    """Run mandatory v0.2 static validation before policy or execution."""
    if not state.plan:
        return state

    if state.plan.interaction_state == InteractionState.AWAITING_DISAMBIGUATION:
        return state

    result = validate_plan(state.plan, build_default_capability_registry())
    state.validation_result = result
    record_role_proposal(
        state,
        role=ReasoningRole.SUPERVISOR,
        proposal_type="coordination",
        payload={
            "validation_valid": result.valid,
            "error_codes": [error.code for error in result.errors],
        },
        deterministic_layer="validate_node",
        attributable_step_id=state.current_step_id,
        consumes_redacted_inputs_only=True,
    )

    if result.valid:
        return state

    state.plan.interaction_state = InteractionState.FAILED
    state.plan.status = "failed"
    first_error = result.errors[0]
    state.response = f"Plan validation failed: {first_error.message}"

    step = state.plan.next_executable_step()
    if step:
        log_graph_event(
            state,
            step=step,
            status="validation_failed",
            summary=state.response,
            action_taken={
                "validation_result": result.model_dump(),
                "capability": step.capability,
                "args": step.args,
            },
        )

    return state
