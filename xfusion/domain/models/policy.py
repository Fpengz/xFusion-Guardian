from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from xfusion.domain.enums import ApprovalMode, PolicyDecisionValue, RiskLevel, RiskTier


class StepRiskContract(BaseModel):
    """Normalized deterministic risk contract for one capability invocation."""

    model_config = ConfigDict(extra="forbid")

    risk_level: str = Field(pattern="^(low|medium|high|critical)$")
    requires_confirmation: bool
    confirmation_type: str = Field(pattern="^(none|user|admin)$")
    deny_code: str | None = None
    deny_reason_text: str | None = None
    # Deprecated but retained for compatibility with existing tests/consumers.
    deny_reason: str | None = None
    side_effects: list[str] = Field(default_factory=list)
    reversibility: str = Field(pattern="^(reversible|partially_reversible|destructive)$")
    privilege_required: bool


class PolicyDecision(BaseModel):
    """Authoritative v0.2 policy result for one normalized capability invocation."""

    model_config = ConfigDict(extra="forbid")

    decision: PolicyDecisionValue
    matched_rule_id: str = Field(min_length=1)
    risk_tier: RiskTier
    approval_mode: ApprovalMode
    constraints_applied: list[str] = Field(default_factory=list)
    reason_codes: list[str] = Field(default_factory=list)
    confirmation_type: str = Field(pattern="^(none|user|admin)$")
    deny_code: str | None = None
    explainability_record: dict[str, Any] = Field(default_factory=dict)
    reason_text: str = Field(min_length=1)
    # Deprecated but retained for compatibility.
    reason: str = Field(min_length=1)
    risk_contract: StepRiskContract | None = None

    @property
    def is_allowed(self) -> bool:
        return self.decision == PolicyDecisionValue.ALLOW

    @property
    def requires_approval(self) -> bool:
        return self.decision == PolicyDecisionValue.REQUIRE_CONFIRMATION

    @property
    def is_denied(self) -> bool:
        return self.decision == PolicyDecisionValue.DENY

    @property
    def risk_level(self) -> RiskLevel:
        """Derived convenience mapping used by graph flow and tests."""
        if self.risk_contract:
            return {
                "low": RiskLevel.LOW,
                "medium": RiskLevel.MEDIUM,
                "high": RiskLevel.HIGH,
                "critical": RiskLevel.FORBIDDEN,
            }[self.risk_contract.risk_level]
        return {
            RiskTier.TIER_0: RiskLevel.LOW,
            RiskTier.TIER_1: RiskLevel.MEDIUM,
            RiskTier.TIER_2: RiskLevel.HIGH,
            RiskTier.TIER_3: RiskLevel.FORBIDDEN,
        }[self.risk_tier]
