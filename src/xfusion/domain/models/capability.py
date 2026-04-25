from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from xfusion.domain.enums import ApprovalMode, RiskTier


class RuntimeConstraints(BaseModel):
    """Deterministic runtime limits for one capability adapter."""

    model_config = ConfigDict(extra="forbid")

    timeout_sec: float = Field(default=30.0, gt=0)
    max_stdout_bytes: int = Field(default=100_000, ge=0)
    max_stderr_bytes: int = Field(default=100_000, ge=0)
    network_access: str = "denied"
    interactive_tty: bool = False
    working_directory: str = "."


class CapabilityDefinition(BaseModel):
    """Code-defined v0.2 capability contract."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1)
    version: int = Field(ge=1)
    verb: str = Field(min_length=1)
    object: str = Field(min_length=1)
    risk_tier: RiskTier
    approval_mode: ApprovalMode
    allowed_environments: list[str] = Field(default_factory=list)
    allowed_actor_types: list[str] = Field(default_factory=list)
    scope_model: dict[str, Any] = Field(default_factory=dict)
    input_schema: dict[str, Any] = Field(default_factory=dict)
    output_schema: dict[str, Any] = Field(default_factory=dict)
    runtime_constraints: RuntimeConstraints = Field(default_factory=RuntimeConstraints)
    adapter_id: str = Field(min_length=1)
    is_read_only: bool
    preview_builder: str = Field(min_length=1)
    verification_recommendation: str = Field(min_length=1)
    redaction_policy: str = Field(min_length=1)
