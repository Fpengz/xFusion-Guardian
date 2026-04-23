from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from xfusion.domain.enums import ApprovalMode, PolicyDecisionValue, RiskLevel, RiskTier


class PolicyDecision(BaseModel):
    """Authoritative v0.2 policy result for one normalized capability invocation."""

    model_config = ConfigDict(extra="forbid")

    decision: PolicyDecisionValue
    matched_rule_id: str = Field(min_length=1)
    risk_tier: RiskTier
    approval_mode: ApprovalMode
    constraints_applied: list[str] = Field(default_factory=list)
    reason_codes: list[str] = Field(default_factory=list)
    explainability_record: dict[str, Any] = Field(default_factory=dict)
    reason: str = Field(min_length=1)

    @property
    def is_allowed(self) -> bool:
        return self.decision == PolicyDecisionValue.ALLOW

    @property
    def requires_approval(self) -> bool:
        return self.decision == PolicyDecisionValue.REQUIRE_APPROVAL

    @property
    def is_denied(self) -> bool:
        return self.decision == PolicyDecisionValue.DENY

    @property
    def allowed(self) -> bool:
        """Transitional read-only compatibility view; not part of model_dump()."""
        return self.decision in {PolicyDecisionValue.ALLOW, PolicyDecisionValue.REQUIRE_APPROVAL}

    @property
    def requires_confirmation(self) -> bool:
        """Transitional read-only compatibility view; v0.2 callers use requires_approval."""
        return self.requires_approval

    @property
    def risk_level(self) -> RiskLevel:
        """Transitional v0.1 label for old verification-suite expectations."""
        return {
            RiskTier.TIER_0: RiskLevel.LOW,
            RiskTier.TIER_1: RiskLevel.MEDIUM,
            RiskTier.TIER_2: RiskLevel.HIGH,
            RiskTier.TIER_3: RiskLevel.FORBIDDEN,
        }[self.risk_tier]
