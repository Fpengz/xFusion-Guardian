from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from xfusion.domain.enums import RiskLevel


class PolicyDecision(BaseModel):
    """Deterministic authorization result for a planned step."""

    model_config = ConfigDict(extra="forbid")

    risk_level: RiskLevel
    allowed: bool
    requires_confirmation: bool
    reason: str = Field(min_length=1)
