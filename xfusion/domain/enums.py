from __future__ import annotations

from enum import StrEnum


class InteractionState(StrEnum):
    AWAITING_DISAMBIGUATION = "awaiting_disambiguation"
    AWAITING_CONFIRMATION = "awaiting_confirmation"
    EXECUTING = "executing"
    COMPLETED = "completed"
    REFUSED = "refused"
    ABORTED = "aborted"
    FAILED = "failed"


class StepStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    SKIPPED = "skipped"
    REFUSED = "refused"


class RiskLevel(StrEnum):
    NONE = "none"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    FORBIDDEN = "forbidden"
