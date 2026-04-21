from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class VerificationResult(BaseModel):
    """Result of post-execution verification."""

    model_config = ConfigDict(extra="forbid")

    success: bool
    method: str = Field(min_length=1)
    summary: str = Field(min_length=1)
    outcome: str = Field(default="unknown")
    details: dict[str, object] = Field(default_factory=dict)
