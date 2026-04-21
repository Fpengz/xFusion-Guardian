from __future__ import annotations

from typing import Any

from xfusion.domain.enums import InteractionState, StepStatus
from xfusion.graph.state import AgentGraphState


def resolve_parameter(param: Any, step_outputs: dict[str, dict[str, Any]]) -> Any:
    """Resolve reference parameter like {'ref': 'step_id.key[index]' or 'step_id.key'}."""
    if not isinstance(param, dict) or "ref" not in param:
        return param

    ref = str(param["ref"])
    try:
        # Format: step_id.key or step_id.key[index]
        parts = ref.split(".", 1)
        if len(parts) != 2:
            raise ValueError(f"Invalid reference format: {ref}")

        step_id, attr = parts
        if step_id not in step_outputs:
            raise ValueError(f"Referenced step '{step_id}' output not found.")

        output_data = step_outputs[step_id]

        # Check for index access like pids[0]
        if "[" in attr and attr.endswith("]"):
            key, idx_str = attr.rstrip("]").split("[", 1)
            idx = int(idx_str)
            val = output_data[key]
            if not isinstance(val, list):
                raise ValueError(f"Attribute '{key}' is not a list.")
            return val[idx]
        else:
            return output_data[attr]
    except (ValueError, KeyError, IndexError) as e:
        raise ValueError(f"Failed to resolve reference '{ref}': {e}") from e


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

    # Resolve parameters
    resolved_params = {}
    try:
        for k, v in step.parameters.items():
            resolved_params[k] = resolve_parameter(v, state.step_outputs)
    except ValueError as e:
        step.status = StepStatus.FAILED
        state.response = f"Parameter resolution failed: {e}"
        return state

    # Execute with resolved parameters
    output = registry.execute(step.tool, resolved_params)

    # Store output in state for real verification AND for downstream steps
    state.last_tool_output = output.data
    state.step_outputs[step.step_id] = output.data
    state.verification_result = None  # Clear previous

    # Tool failure still sets step status to FAILED
    if "error" in output.data:
        step.status = StepStatus.FAILED
        # We don't set InteractionState.FAILED here, update_node will handle it
        state.response = f"Step failed: {output.summary}"
    else:
        # We do NOT set SUCCESS here. Verification node must do that.
        state.response = output.summary

    return state
