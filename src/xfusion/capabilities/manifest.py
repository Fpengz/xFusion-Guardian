from __future__ import annotations

from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from xfusion.capabilities.registry import CapabilityRegistry
from xfusion.capabilities.schema import validate_schema_contract
from xfusion.domain.enums import ApprovalMode, RiskTier
from xfusion.domain.models.capability import (
    CapabilityDefinition,
    CapabilityPrompt,
    RuntimeConstraints,
)
from xfusion.execution.allowlist import ExecutableRegistry, ExecutableRegistryError


class CapabilityManifestError(ValueError):
    """Raised when v0.2.5 capability manifests fail closed at startup."""


class ArgvValueToken(BaseModel):
    model_config = ConfigDict(extra="forbid")

    value: str = Field(min_length=1)

    @model_validator(mode="after")
    def reject_template_syntax(self) -> ArgvValueToken:
        if "{{" in self.value or "}}" in self.value:
            raise ValueError("argv value token contains template syntax")
        return self


class ArgvArgToken(BaseModel):
    model_config = ConfigDict(extra="forbid")

    arg: str = Field(min_length=1)

    @model_validator(mode="after")
    def reject_partial_binding(self) -> ArgvArgToken:
        if "{{" in self.arg or "}}" in self.arg:
            raise ValueError("argv arg token must name one input field")
        return self


class ExecutionConstraints(BaseModel):
    model_config = ConfigDict(extra="forbid")

    timeout_ms: int = Field(default=30_000, gt=0, le=120_000)
    max_stdout_bytes: int = Field(default=100_000, ge=0, le=1_000_000)
    max_stderr_bytes: int = Field(default=100_000, ge=0, le=1_000_000)
    env_allowlist: list[str] = Field(default_factory=list)


class ArgvExecution(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal["argv"]
    executable: str = Field(min_length=1)
    argv: list[ArgvValueToken | ArgvArgToken] = Field(default_factory=list)
    constraints: ExecutionConstraints = Field(default_factory=ExecutionConstraints)


class PythonAdapterExecution(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal["python_adapter"]
    adapter_id: str = Field(min_length=1)
    constraints: ExecutionConstraints = Field(default_factory=ExecutionConstraints)


class CapabilityManifest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    api_version: Literal["xfusion.capability/v1"]
    name: str = Field(min_length=1)
    version: int = Field(ge=1)
    short_description: str = Field(min_length=1)
    risk_tier: RiskTier
    approval_mode: ApprovalMode
    is_read_only: bool
    side_effect_classification: Literal[
        "none",
        "read_only_external",
        "reversible_local",
        "persistent_local",
        "privileged_system",
        "destructive",
        "network_external",
    ]
    input_schema: dict[str, Any]
    output_schema: dict[str, Any]
    target_constraints: dict[str, Any] = Field(default_factory=dict)
    execution: ArgvExecution | PythonAdapterExecution = Field(discriminator="type")
    normalizer: dict[str, Any] = Field(default_factory=dict)
    verification: dict[str, Any]
    redaction_policy: str = Field(min_length=1)
    prompt: CapabilityPrompt

    def compile(self, executables: ExecutableRegistry) -> CapabilityDefinition:
        errors = _validate_manifest_contract(self, executables)
        if errors:
            raise CapabilityManifestError("; ".join(errors))
        constraints = self.execution.constraints
        adapter_id = (
            f"argv:{self.execution.executable}"
            if isinstance(self.execution, ArgvExecution)
            else self.execution.adapter_id
        )
        return CapabilityDefinition(
            name=self.name,
            version=self.version,
            verb=self.name.rsplit(".", 1)[-1],
            object=self.name.split(".", 1)[0],
            risk_tier=self.risk_tier,
            approval_mode=self.approval_mode,
            allowed_environments=["dev", "staging", "production"],
            allowed_actor_types=["operator", "assistant"],
            scope_model=self.target_constraints,
            input_schema=self.input_schema,
            output_schema=self.output_schema,
            runtime_constraints=RuntimeConstraints(
                timeout_sec=constraints.timeout_ms / 1000,
                max_stdout_bytes=constraints.max_stdout_bytes,
                max_stderr_bytes=constraints.max_stderr_bytes,
                network_access="denied",
                interactive_tty=False,
                working_directory=".",
            ),
            adapter_id=adapter_id,
            is_read_only=self.is_read_only,
            preview_builder="default",
            verification_recommendation=str(self.verification.get("type", "output_check")),
            redaction_policy=self.redaction_policy,
            short_description=self.short_description,
            target_constraints=self.target_constraints,
            execution_binding=self.execution.model_dump(),
            verification=self.verification,
            side_effect_classification=self.side_effect_classification,
            prompt=self.prompt,
        )


def load_capability_manifests(
    paths: list[Path],
    *,
    executables: ExecutableRegistry,
) -> CapabilityRegistry:
    errors: list[str] = []
    capabilities: list[CapabilityDefinition] = []
    for path in paths:
        try:
            raw = yaml.safe_load(path.read_text(encoding="utf-8"))
            manifest = CapabilityManifest.model_validate(raw)
            capabilities.append(manifest.compile(executables))
        except ValidationError as exc:
            raw_errors = _raw_manifest_errors(raw if isinstance(raw, dict) else {}, executables)
            detail = "; ".join(raw_errors + [str(exc)])
            errors.append(f"{path}: {detail}")
        except (OSError, CapabilityManifestError, ExecutableRegistryError) as exc:
            errors.append(f"{path}: {exc}")
    if errors:
        raise CapabilityManifestError("; ".join(errors))
    try:
        return CapabilityRegistry(capabilities)
    except ValueError as exc:
        raise CapabilityManifestError(str(exc)) from exc


def _validate_manifest_contract(
    manifest: CapabilityManifest,
    executables: ExecutableRegistry,
) -> list[str]:
    errors: list[str] = []
    for schema_name, schema in (
        ("input_schema", manifest.input_schema),
        ("output_schema", manifest.output_schema),
    ):
        result = validate_schema_contract(schema)
        for error in result.errors:
            errors.append(f"{schema_name}: {error}")
    if isinstance(manifest.execution, ArgvExecution):
        try:
            executables.require(manifest.execution.executable)
        except ExecutableRegistryError as exc:
            errors.append(str(exc))
        properties = manifest.input_schema.get("properties", {})
        if not isinstance(properties, dict):
            properties = {}
        for token in manifest.execution.argv:
            if isinstance(token, ArgvArgToken) and token.arg not in properties:
                errors.append(f"argv arg token references unknown input field '{token.arg}'")
    if not manifest.verification.get("type"):
        errors.append("verification.type is required")
    return errors


def _raw_manifest_errors(raw: dict[str, Any], executables: ExecutableRegistry) -> list[str]:
    errors: list[str] = []
    execution = raw.get("execution")
    if not isinstance(execution, dict):
        return errors
    if execution.get("type") == "argv":
        executable = execution.get("executable")
        if isinstance(executable, str):
            try:
                executables.require(executable)
            except ExecutableRegistryError as exc:
                errors.append(str(exc))
    return errors
