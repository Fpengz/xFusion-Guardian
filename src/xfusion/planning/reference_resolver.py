from __future__ import annotations

from typing import Any

from xfusion.domain.enums import StepStatus
from xfusion.domain.models.execution_plan import ExecutionPlan
from xfusion.planning.validator import REFERENCE_RE


def _resolve_output_path(output_data: dict[str, Any], attr: str) -> Any:
    if "[" in attr and attr.endswith("]"):
        key, idx_str = attr.rstrip("]").split("[", 1)
        idx = int(idx_str)
        value = output_data[key]
        if not isinstance(value, list):
            raise ValueError(f"Attribute '{key}' is not a list.")
        return value[idx]
    return output_data[attr]


def _require_authorized_output(
    *,
    plan: ExecutionPlan,
    step_id: str,
    authorized_outputs: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    upstream_step = next((step for step in plan.steps if step.step_id == step_id), None)
    if upstream_step is None:
        raise ValueError(f"Referenced step '{step_id}' does not exist.")
    if upstream_step.status != StepStatus.SUCCESS or not upstream_step.authorized_output_accepted:
        raise ValueError(
            f"Referenced step '{step_id}' is not a successful authorized upstream output."
        )
    if step_id not in authorized_outputs:
        raise ValueError(f"Referenced step '{step_id}' output not found.")
    return authorized_outputs[step_id]


def resolve_reference(
    reference: str,
    *,
    plan: ExecutionPlan,
    authorized_outputs: dict[str, dict[str, Any]],
) -> Any:
    """Resolve canonical v0.2 $steps.<id>.outputs.<field> references."""
    match = REFERENCE_RE.match(reference)
    if match is None:
        raise ValueError(f"Invalid reference syntax: {reference}")

    step_id = match.group("step_id")
    field = match.group("field")
    index = match.group("index")
    attr = f"{field}[{index}]" if index is not None else field
    output_data = _require_authorized_output(
        plan=plan,
        step_id=step_id,
        authorized_outputs=authorized_outputs,
    )
    try:
        return _resolve_output_path(output_data, attr)
    except (KeyError, IndexError, ValueError) as e:
        raise ValueError(f"Failed to resolve reference '{reference}': {e}") from e


def resolve_legacy_ref(
    ref: str,
    *,
    plan: ExecutionPlan,
    authorized_outputs: dict[str, dict[str, Any]],
) -> Any:
    """Reject legacy references; v0.2 requires canonical $steps references."""
    raise ValueError(
        "Legacy reference syntax is forbidden in v0.2; "
        f"use canonical $steps.<id>.outputs.<field> syntax instead: {ref}"
    )


def resolve_value(
    value: Any,
    *,
    plan: ExecutionPlan,
    authorized_outputs: dict[str, dict[str, Any]],
) -> Any:
    if isinstance(value, str) and value.startswith("$steps."):
        return resolve_reference(value, plan=plan, authorized_outputs=authorized_outputs)

    if isinstance(value, dict) and "ref" in value:
        return resolve_legacy_ref(
            str(value["ref"]),
            plan=plan,
            authorized_outputs=authorized_outputs,
        )

    if isinstance(value, dict):
        return {
            key: resolve_value(nested, plan=plan, authorized_outputs=authorized_outputs)
            for key, nested in value.items()
        }

    if isinstance(value, list):
        return [
            resolve_value(nested, plan=plan, authorized_outputs=authorized_outputs)
            for nested in value
        ]

    return value


def resolve_args(
    args: dict[str, object],
    *,
    plan: ExecutionPlan,
    authorized_outputs: dict[str, dict[str, Any]] | None = None,
    step_outputs: dict[str, dict[str, Any]] | None = None,
) -> dict[str, object]:
    if authorized_outputs is None:
        raise ValueError(
            "authorized_outputs is required for v0.2 reference resolution; "
            "legacy step_outputs fallback is forbidden."
        )
    return {
        key: resolve_value(value, plan=plan, authorized_outputs=authorized_outputs)
        for key, value in args.items()
    }
