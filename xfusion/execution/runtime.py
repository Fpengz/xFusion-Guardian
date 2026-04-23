from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Protocol

from pydantic import BaseModel, ConfigDict, Field

from xfusion.capabilities.schema import validate_schema_value
from xfusion.domain.enums import FailureClass
from xfusion.domain.models.capability import CapabilityDefinition
from xfusion.security.redaction import redact_value
from xfusion.tools.base import ToolOutput


class CapabilityExecutor(Protocol):
    def execute(self, name: str, parameters: dict[str, Any]) -> ToolOutput: ...


class ControlledInvocation(BaseModel):
    """Audited invocation passed to the controlled adapter runtime."""

    model_config = ConfigDict(extra="forbid")

    capability: str
    adapter_id: str
    normalized_args: dict[str, Any]
    runtime_constraints: dict[str, Any]
    started_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class AdapterOutcome(BaseModel):
    """Authoritative adapter result after schema validation and redaction."""

    model_config = ConfigDict(extra="forbid")

    invocation: ControlledInvocation
    status: str
    normalized_output: dict[str, Any]
    summary: str
    redaction_metadata: dict[str, Any]
    ended_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


def _merge_counts(*metas: dict[str, Any]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for meta in metas:
        for key, count in dict(meta.get("counts", {})).items():
            counts[key] = counts.get(key, 0) + int(count)
    return counts


def _safe_redact(value: Any) -> tuple[Any, dict[str, Any]]:
    try:
        return redact_value(value)
    except Exception:  # noqa: BLE001 - redaction failure must fail closed without raw exposure.
        return (
            {
                "failure_class": FailureClass.REDACTION_FAILURE.value,
                "error": "redaction failed; raw value withheld",
            },
            {"redacted": True, "counts": {}, "redaction_failed": True},
        )


def _failure_outcome(
    *,
    invocation: ControlledInvocation,
    status: FailureClass | str,
    failure: dict[str, Any],
    summary: str,
) -> AdapterOutcome:
    redacted_failure, failure_meta = _safe_redact(failure)
    redacted_summary, summary_meta = _safe_redact(summary)
    counts = _merge_counts(failure_meta, summary_meta)
    redaction_failed = bool(failure_meta.get("redaction_failed")) or bool(
        summary_meta.get("redaction_failed")
    )
    final_status = FailureClass.REDACTION_FAILURE.value if redaction_failed else str(status)
    if redaction_failed:
        redacted_failure = {
            "failure_class": FailureClass.REDACTION_FAILURE.value,
            "error": "redaction failed; raw value withheld",
        }
        redacted_summary = "Redaction failed; raw adapter data was withheld."
    return AdapterOutcome(
        invocation=invocation,
        status=final_status,
        normalized_output=redacted_failure,
        summary=str(redacted_summary),
        redaction_metadata={
            "redacted": bool(counts) or redaction_failed,
            "counts": counts,
            "redaction_failed": redaction_failed,
        },
    )


class ControlledAdapterRuntime:
    """Trust-boundary wrapper around registered typed capability adapters.

    The executor may call OS-facing adapters, but this runtime owns the
    deterministic boundary around runtime constraints, output schema validation,
    redaction, and normalized failure records.
    """

    def __init__(self, executor: CapabilityExecutor) -> None:
        self.executor = executor

    def execute(
        self,
        *,
        capability: CapabilityDefinition,
        normalized_args: dict[str, Any],
    ) -> AdapterOutcome:
        invocation = ControlledInvocation(
            capability=capability.name,
            adapter_id=capability.adapter_id,
            normalized_args=normalized_args,
            runtime_constraints=capability.runtime_constraints.model_dump(),
        )
        failure = self._validate_runtime_constraints(capability=capability, args=normalized_args)
        if failure:
            return AdapterOutcome(
                invocation=invocation,
                status="runtime_rejected",
                normalized_output={"error": failure},
                summary=f"Runtime rejected capability '{capability.name}': {failure}",
                redaction_metadata={"redacted": False, "counts": {}},
            )

        try:
            output = self.executor.execute(capability.name, normalized_args)
        except TimeoutError as exc:
            raw_failure = {
                "failure_class": FailureClass.RUNTIME_TIMEOUT.value,
                "error": str(exc),
                "exception_type": exc.__class__.__name__,
            }
            return _failure_outcome(
                invocation=invocation,
                status=FailureClass.RUNTIME_TIMEOUT,
                failure=raw_failure,
                summary=f"Runtime timed out for capability '{capability.name}': {exc}",
            )
        except Exception as exc:  # noqa: BLE001 - adapter boundary must normalize all failures.
            raw_failure = {
                "failure_class": FailureClass.ADAPTER_FAILURE.value,
                "error": str(exc),
                "exception_type": exc.__class__.__name__,
            }
            return _failure_outcome(
                invocation=invocation,
                status=FailureClass.ADAPTER_FAILURE,
                failure=raw_failure,
                summary=f"Adapter failed for capability '{capability.name}': {exc}",
            )

        try:
            output_data = output.data
            output_summary = output.summary
            schema_result = validate_schema_value(output_data, capability.output_schema)
            if not schema_result.valid:
                failure = {
                    "failure_class": FailureClass.OUTPUT_SCHEMA_VALIDATION_FAILURE.value,
                    "capability": capability.name,
                    "adapter_id": capability.adapter_id,
                    "validation_errors": schema_result.errors,
                }
                return _failure_outcome(
                    invocation=invocation,
                    status="output_schema_validation_failed",
                    failure=failure,
                    summary=(
                        "Adapter output failed schema validation for capability "
                        f"'{capability.name}'."
                    ),
                )

            redacted_data, redaction_metadata = _safe_redact(output_data)
            redacted_summary, summary_meta = _safe_redact(output_summary)
            redaction_failed = bool(redaction_metadata.get("redaction_failed")) or bool(
                summary_meta.get("redaction_failed")
            )
            if redaction_failed:
                return _failure_outcome(
                    invocation=invocation,
                    status=FailureClass.REDACTION_FAILURE,
                    failure={
                        "failure_class": FailureClass.REDACTION_FAILURE.value,
                        "error": "redaction failed; raw adapter data withheld",
                    },
                    summary="Redaction failed; raw adapter data was withheld.",
                )
            counts = _merge_counts(redaction_metadata, summary_meta)
            return AdapterOutcome(
                invocation=invocation,
                status="failed" if "error" in redacted_data else "succeeded",
                normalized_output=redacted_data,
                summary=str(redacted_summary),
                redaction_metadata={"redacted": bool(counts), "counts": counts},
            )
        except Exception as exc:  # noqa: BLE001 - output handling is inside the trust boundary.
            return _failure_outcome(
                invocation=invocation,
                status=FailureClass.INTERNAL_SYSTEM_FAILURE,
                failure={
                    "failure_class": FailureClass.INTERNAL_SYSTEM_FAILURE.value,
                    "error": str(exc),
                    "exception_type": exc.__class__.__name__,
                },
                summary=f"Internal system failure while handling capability '{capability.name}'.",
            )

    def _validate_runtime_constraints(
        self, *, capability: CapabilityDefinition, args: dict[str, Any]
    ) -> str | None:
        constraints = capability.runtime_constraints
        if constraints.interactive_tty:
            return "interactive_tty_forbidden"
        if constraints.network_access != "denied":
            return "network_must_be_explicitly_policy_allowed"
        if constraints.timeout_sec <= 0 or constraints.timeout_sec > 120:
            return "timeout_out_of_bounds"
        if constraints.max_stdout_bytes > 1_000_000 or constraints.max_stderr_bytes > 1_000_000:
            return "byte_limit_out_of_bounds"
        if "command" in args:
            return "free_form_command_arg_forbidden"
        if capability.adapter_id in {"run_command", "shell", "bash", "sh"}:
            return "prohibited_adapter"
        return None
