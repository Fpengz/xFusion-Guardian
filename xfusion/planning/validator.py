from __future__ import annotations

import re
from collections import defaultdict, deque
from collections.abc import Iterable
from typing import Any, cast

from pydantic import BaseModel, ConfigDict, Field

from xfusion.capabilities.registry import CapabilityRegistry
from xfusion.domain.models.capability import CapabilityDefinition
from xfusion.domain.models.execution_plan import ExecutionPlan, PlanStep

REFERENCE_RE = re.compile(
    r"^\$steps\.(?P<step_id>[A-Za-z_][A-Za-z0-9_-]*)\.outputs\."
    r"(?P<field>[A-Za-z_][A-Za-z0-9_]*)(?:\[(?P<index>[0-9]+)\])?$"
)


class PlanValidationError(BaseModel):
    """Structured v0.2 plan validation error."""

    model_config = ConfigDict(extra="forbid")

    code: str = Field(min_length=1)
    message: str = Field(min_length=1)
    step_id: str | None = None


class PlanValidationResult(BaseModel):
    """Validation result for a v0.2 execution plan."""

    model_config = ConfigDict(extra="forbid")

    valid: bool
    errors: list[PlanValidationError] = Field(default_factory=list)


def _iter_references(value: Any) -> Iterable[str]:
    if isinstance(value, str) and value.startswith("$steps."):
        yield value
    elif isinstance(value, dict):
        for nested in value.values():
            yield from _iter_references(nested)
    elif isinstance(value, list):
        for nested in value:
            yield from _iter_references(nested)


def _iter_legacy_refs(value: Any) -> Iterable[str]:
    if isinstance(value, dict) and "ref" in value:
        yield str(value["ref"])
    elif isinstance(value, dict):
        for nested in value.values():
            yield from _iter_legacy_refs(nested)
    elif isinstance(value, list):
        for nested in value:
            yield from _iter_legacy_refs(nested)


def _split_legacy_ref(ref: str) -> tuple[str, str] | None:
    parts = ref.split(".", 1)
    if len(parts) != 2:
        return None
    step_id, attr = parts
    field = attr.split("[", 1)[0]
    if not step_id or not field:
        return None
    return step_id, field


def _declared_output_fields(capability_output_schema: dict[str, object]) -> set[str]:
    properties = capability_output_schema.get("properties")
    if not isinstance(properties, dict):
        return set()
    return {str(field) for field in properties}


def _validate_acyclic(steps: list[PlanStep]) -> bool:
    step_ids = {str(step.step_id) for step in steps}
    incoming_count = {step_id: 0 for step_id in step_ids}
    outgoing: dict[str, list[str]] = defaultdict(list)

    for step in steps:
        step_id = str(step.step_id)
        for dep in step.dependencies:
            if dep not in step_ids:
                continue
            incoming_count[step_id] += 1
            outgoing[dep].append(step_id)

    queue = deque(step_id for step_id, count in incoming_count.items() if count == 0)
    visited = 0
    while queue:
        step_id = queue.popleft()
        visited += 1
        for dependent in outgoing[step_id]:
            incoming_count[dependent] -= 1
            if incoming_count[dependent] == 0:
                queue.append(dependent)

    return visited == len(step_ids)


def _schema_type_matches(value: object, schema: dict[str, object]) -> bool:
    expected_type = schema.get("type")
    if expected_type == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if expected_type == "number":
        return isinstance(value, int | float) and not isinstance(value, bool)
    if expected_type == "string":
        return isinstance(value, str)
    if expected_type == "boolean":
        return isinstance(value, bool)
    if expected_type == "array":
        return isinstance(value, list)
    if expected_type == "object":
        return isinstance(value, dict)
    return True


def _schema_constraint_errors(value: object, schema: dict[str, object]) -> list[str]:
    errors: list[str] = []
    enum_values = schema.get("enum")
    if isinstance(enum_values, list) and value not in enum_values:
        errors.append("arg_enum_violation")

    if isinstance(value, int | float) and not isinstance(value, bool):
        minimum = schema.get("minimum")
        maximum = schema.get("maximum")
        if isinstance(minimum, int | float) and value < minimum:
            errors.append("arg_range_violation")
        if isinstance(maximum, int | float) and value > maximum:
            errors.append("arg_range_violation")

    if isinstance(value, str):
        min_length = schema.get("minLength")
        max_length = schema.get("maxLength")
        if isinstance(min_length, int) and len(value) < min_length:
            errors.append("arg_length_violation")
        if isinstance(max_length, int) and len(value) > max_length:
            errors.append("arg_length_violation")

    if isinstance(value, list):
        min_items = schema.get("minItems")
        max_items = schema.get("maxItems")
        if isinstance(min_items, int) and len(value) < min_items:
            errors.append("arg_length_violation")
        if isinstance(max_items, int) and len(value) > max_items:
            errors.append("arg_length_violation")

    return errors


def _validate_literal_args(
    *,
    step: PlanStep,
    input_schema: dict[str, object],
    errors: list[PlanValidationError],
) -> None:
    properties = input_schema.get("properties")
    required = input_schema.get("required")
    if not isinstance(properties, dict):
        properties = {}
    if not isinstance(required, list):
        required = []
    typed_properties = cast(dict[str, object], properties)

    for required_name in required:
        if str(required_name) not in step.args:
            errors.append(
                PlanValidationError(
                    code="missing_required_arg",
                    step_id=step.step_id,
                    message=f"Step '{step.step_id}' missing required arg '{required_name}'.",
                )
            )

    for arg_name, arg_value in step.args.items():
        if arg_name not in typed_properties:
            errors.append(
                PlanValidationError(
                    code="unknown_arg",
                    step_id=step.step_id,
                    message=f"Step '{step.step_id}' arg '{arg_name}' is not in capability schema.",
                )
            )
            continue
        if isinstance(arg_value, str) and arg_value.startswith("$steps."):
            continue
        if isinstance(arg_value, dict) and "ref" in arg_value:
            continue
        arg_schema = typed_properties[arg_name]
        if isinstance(arg_schema, dict) and not _schema_type_matches(
            arg_value, cast(dict[str, object], arg_schema)
        ):
            errors.append(
                PlanValidationError(
                    code="arg_type_mismatch",
                    step_id=step.step_id,
                    message=f"Step '{step.step_id}' arg '{arg_name}' does not match schema.",
                )
            )
            continue
        if isinstance(arg_schema, dict):
            for constraint_code in _schema_constraint_errors(
                arg_value, cast(dict[str, object], arg_schema)
            ):
                errors.append(
                    PlanValidationError(
                        code=constraint_code,
                        step_id=step.step_id,
                        message=(
                            f"Step '{step.step_id}' arg '{arg_name}' violates "
                            "capability schema constraints."
                        ),
                    )
                )


def validate_plan(
    plan: ExecutionPlan,
    registry: CapabilityRegistry,
) -> PlanValidationResult:
    """Validate v0.2 static plan constraints before policy or execution."""
    errors: list[PlanValidationError] = []
    step_ids = [str(step.step_id) for step in plan.steps]
    step_id_set = set(step_ids)

    if len(step_ids) != len(step_id_set):
        errors.append(
            PlanValidationError(
                code="duplicate_step_id",
                message="Plan contains duplicate step ids.",
            )
        )

    if not _validate_acyclic(plan.steps):
        errors.append(
            PlanValidationError(
                code="cyclic_dependency_graph",
                message="Plan dependency graph contains a cycle.",
            )
        )

    has_mutation = False
    capabilities_by_step: dict[str, CapabilityDefinition] = {}

    for step in plan.steps:
        capability_name = str(step.capability)
        capability = registry.get(capability_name)
        if capability is None:
            errors.append(
                PlanValidationError(
                    code="unknown_capability",
                    step_id=step.step_id,
                    message=f"Unknown capability '{capability_name}'.",
                )
            )
            continue

        capabilities_by_step[str(step.step_id)] = capability
        has_mutation = has_mutation or not capability.is_read_only
        _validate_literal_args(step=step, input_schema=capability.input_schema, errors=errors)

        for dep in step.dependencies:
            if dep not in step_id_set:
                errors.append(
                    PlanValidationError(
                        code="unknown_dependency",
                        step_id=step.step_id,
                        message=f"Step '{step.step_id}' depends on unknown step '{dep}'.",
                    )
                )

        for reference in _iter_references(step.args):
            match = REFERENCE_RE.match(reference)
            if match is None:
                errors.append(
                    PlanValidationError(
                        code="invalid_reference_syntax",
                        step_id=step.step_id,
                        message=f"Invalid reference syntax: {reference}",
                    )
                )
                continue

            ref_step_id = match.group("step_id")
            ref_field = match.group("field")
            if ref_step_id not in step_id_set:
                errors.append(
                    PlanValidationError(
                        code="unknown_reference_step",
                        step_id=step.step_id,
                        message=f"Reference points to unknown step '{ref_step_id}'.",
                    )
                )
                continue

            if ref_step_id not in step.dependencies:
                errors.append(
                    PlanValidationError(
                        code="reference_not_dependency",
                        step_id=step.step_id,
                        message=(
                            f"Reference to '{ref_step_id}' is not declared as a dependency "
                            f"of step '{step.step_id}'."
                        ),
                    )
                )

            upstream_capability = capabilities_by_step.get(ref_step_id)
            if upstream_capability is None:
                upstream_step = next(
                    (candidate for candidate in plan.steps if candidate.step_id == ref_step_id),
                    None,
                )
                if upstream_step is not None:
                    upstream_capability = registry.get(str(upstream_step.capability))
            if upstream_capability is None:
                continue

            declared_fields = _declared_output_fields(upstream_capability.output_schema)
            if declared_fields and ref_field not in declared_fields:
                errors.append(
                    PlanValidationError(
                        code="unknown_reference_output",
                        step_id=step.step_id,
                        message=(
                            f"Reference field '{ref_field}' is not declared by "
                            f"capability '{upstream_capability.name}'."
                        ),
                    )
                )

        for legacy_ref in _iter_legacy_refs(step.args):
            errors.append(
                PlanValidationError(
                    code="legacy_reference_forbidden",
                    step_id=step.step_id,
                    message=(
                        "Legacy {'ref': ...} references are forbidden in v0.2; "
                        f"use canonical $steps.<id>.outputs.<field> syntax instead: {legacy_ref}"
                    ),
                )
            )

    if has_mutation and not plan.verification_strategy:
        errors.append(
            PlanValidationError(
                code="missing_verification_strategy",
                message="Mutating workflow requires a verification strategy.",
            )
        )

    if has_mutation and not plan.verification_no_meaningful_verifier:
        verification_steps = {
            verification_step_id
            for step in plan.steps
            for verification_step_id in step.verification_step_ids
        }
        has_explicit_verification_step = any(
            step.step_id in verification_steps for step in plan.steps
        )
        if not has_explicit_verification_step and len(plan.steps) > 1:
            errors.append(
                PlanValidationError(
                    code="missing_explicit_verification_step",
                    message=(
                        "Mutating workflow requires an explicit verification step unless "
                        "no meaningful verifier exists."
                    ),
                )
            )

    return PlanValidationResult(valid=not errors, errors=errors)
