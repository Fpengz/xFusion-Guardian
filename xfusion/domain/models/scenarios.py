from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class ExpectedScenario(BaseModel):
    """Expected behavior for one verification scenario."""

    model_config = ConfigDict(extra="forbid")

    plan_length: int = Field(ge=0)
    plan_tools: list[str]
    executed_tools: list[str]
    risk_level: str
    interaction_state: str
    requires_confirmation: bool
    verification_method: str
    verification_outcome: str
    final_status: str
    outcome_contains: list[str]
    refusal_or_fallback: str


class VerificationScenario(BaseModel):
    """YAML-backed verification scenario."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1)
    category: str = Field(min_length=1)
    mode: str = Field(pattern="^(static|fake_tool|live_vm)$")
    language: str = Field(min_length=1)
    input: str = Field(min_length=1)
    preconditions: dict[str, object]
    safe_for_live_execution: bool
    notes: str = ""
    expected: ExpectedScenario
