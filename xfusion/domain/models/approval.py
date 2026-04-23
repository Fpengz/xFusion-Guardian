from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from xfusion.domain.enums import ApprovalMode, RiskTier


class PreviewPayload(BaseModel):
    """Operator-visible preview for an approval-gated capability invocation."""

    model_config = ConfigDict(extra="forbid")

    impacted_target: str
    action_summary: str
    reversibility_estimate: str
    expected_blast_radius: str
    capability: str
    normalized_args: dict[str, Any]
    argument_provenance_summary: dict[str, str]
    rollback_notes: str | None = None
    approval_mode: ApprovalMode
    expiry: datetime


class ApprovalRecord(BaseModel):
    """Typed approval bound to a deterministic action fingerprint."""

    model_config = ConfigDict(extra="forbid")

    approval_id: str = Field(min_length=1)
    plan_id: str = Field(min_length=1)
    step_id: str = Field(min_length=1)
    normalized_capability_set: list[str] = Field(min_length=1)
    target_context: dict[str, Any]
    action_fingerprint: str = Field(min_length=1)
    policy_snapshot_hash: str = Field(min_length=1)
    referenced_output_fingerprints: dict[str, str] = Field(default_factory=dict)
    approval_mode: ApprovalMode
    risk_tier: RiskTier
    adapter_id: str = Field(min_length=1)
    capability_version: int = Field(ge=1)
    preview: PreviewPayload
    typed_confirmation_phrase: str = Field(min_length=1)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    expires_at: datetime = Field(default_factory=lambda: datetime.now(UTC) + timedelta(minutes=10))
    approved_at: datetime | None = None
    invalidated_at: datetime | None = None
    invalidation_reason: str | None = None

    @property
    def is_approved(self) -> bool:
        return self.approved_at is not None and self.invalidated_at is None

    def is_expired(self, now: datetime | None = None) -> bool:
        check_time = now or datetime.now(UTC)
        return check_time >= self.expires_at
