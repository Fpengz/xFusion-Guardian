from __future__ import annotations

from xfusion.capabilities.registry import build_default_capability_registry
from xfusion.domain.enums import InteractionState
from xfusion.graph.auditing import log_graph_event
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
