from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class AuditRecord(BaseModel):
    """Append-only audit record for one plan step."""

    model_config = ConfigDict(extra="forbid")

    timestamp: datetime
    plan_id: str = Field(min_length=1)
    step_id: str = Field(min_length=1)
    interaction_state: str = Field(min_length=1)
    before_state: dict[str, object]
    action_taken: dict[str, object]
    after_state: dict[str, object]
    verification_result: dict[str, object]
    step_started_at: datetime | None = None
    step_ended_at: datetime | None = None
    status: str = Field(min_length=1)
    summary: str = Field(min_length=1)
    execution_surface: str | None = None
    policy_category: str | None = None
    final_risk_category: str | None = None
    impact_scope: dict[str, object] = Field(default_factory=dict)
    agent_risk_assessment: dict[str, object] = Field(default_factory=dict)
    system_risk_envelope: dict[str, object] = Field(default_factory=dict)
    resolution_record: dict[str, object] = Field(default_factory=dict)
    fallback_reason: str | None = None
    integrity_hashes: dict[str, object] = Field(default_factory=dict)
