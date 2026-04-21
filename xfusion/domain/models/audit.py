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
    status: str = Field(min_length=1)
    summary: str = Field(min_length=1)
