from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from xfusion.domain.enums import ApprovalMode, ReasoningRole, RiskTier, VerificationStatus


class VerificationResult(BaseModel):
    """Result of post-execution verification."""

    model_config = ConfigDict(extra="forbid")

    verification_id: str = Field(min_length=1)
    step_id: str = Field(min_length=1)
    success: bool
    method: str = Field(min_length=1)
    summary: str = Field(min_length=1)
    outcome: VerificationStatus = VerificationStatus.INCONCLUSIVE
    failure_class: str | None = None
    details: dict[str, object] = Field(default_factory=dict)
    recorded_at: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())


class RepairTrigger(BaseModel):
    """Why verification triggered a repair path."""

    model_config = ConfigDict(extra="forbid")

    verification_id: str = Field(min_length=1)
    failed_step_id: str = Field(min_length=1)
    verification_method: str = Field(min_length=1)
    verification_outcome: VerificationStatus
    failure_class: str = Field(min_length=1)
    evidence_fingerprint: str = Field(min_length=1)
    summary: str = Field(min_length=1)


class RepairStepDraft(BaseModel):
    """Typed draft for a non-authoritative repair step proposal."""

    model_config = ConfigDict(extra="forbid")

    proposed_step_id: str = Field(min_length=1)
    capability: str = Field(min_length=1)
    args: dict[str, Any] = Field(default_factory=dict)
    depends_on: list[str] = Field(default_factory=list)
    justification: str = Field(min_length=1)
    verification_method: str = Field(min_length=1)
    success_condition: str = Field(min_length=1)
    failure_condition: str = Field(min_length=1)
    fallback_action: str = Field(min_length=1)
    escalation: bool = False


class RepairEquivalenceDecision(BaseModel):
    """Deterministic equivalence decision for repair proposals."""

    model_config = ConfigDict(extra="forbid")

    equivalent: bool
    material_change_fields: list[str] = Field(default_factory=list)
    policy_allows_equivalent_approval_reuse: bool = False
    prior_approval_reusable: bool = False
    reason: str = Field(min_length=1)


class RepairApprovalRequirement(BaseModel):
    """Approval posture for repair execution."""

    model_config = ConfigDict(extra="forbid")

    requires_reapproval: bool
    required_mode: ApprovalMode | None = None
    reason: str = Field(min_length=1)


class RepairProposal(BaseModel):
    """Typed repair proposal linked to failed verification context."""

    model_config = ConfigDict(extra="forbid")

    proposal_id: str = Field(min_length=1)
    proposed_by_role: ReasoningRole = ReasoningRole.VERIFICATION
    trigger: RepairTrigger
    original_step_id: str = Field(min_length=1)
    draft: RepairStepDraft
    equivalence: RepairEquivalenceDecision
    approval_requirement: RepairApprovalRequirement
    prior_approval_id: str | None = None
    prior_risk_tier: RiskTier | None = None
    audit_link: str = Field(min_length=1)
    state: str = Field(pattern="^(proposed|accepted_for_reentry|rejected)$")
    deterministic_reason: str = Field(min_length=1)
    created_at: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())
