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


class RiskTier(StrEnum):
    TIER_0 = "tier_0"
    TIER_1 = "tier_1"
    TIER_2 = "tier_2"
    TIER_3 = "tier_3"


class ApprovalMode(StrEnum):
    AUTO = "auto"
    HUMAN = "human"
    ADMIN = "admin"
    DENY = "deny"


class PolicyDecisionValue(StrEnum):
    ALLOW = "allow"
    REQUIRE_CONFIRMATION = "require_confirmation"
    # Backward-compatible alias; normalized value is require_confirmation.
    REQUIRE_APPROVAL = "require_confirmation"
    DENY = "deny"


class ReasoningRole(StrEnum):
    SUPERVISOR = "supervisor"
    OBSERVATION = "observation"
    DIAGNOSIS = "diagnosis"
    PLANNING = "planning"
    VERIFICATION = "verification"
    EXPLANATION = "explanation"


class VerificationStatus(StrEnum):
    SUCCESS = "success"
    PARTIAL_SUCCESS = "partial_success"
    FAILED = "failed"
    INCONCLUSIVE = "inconclusive"


class FailureClass(StrEnum):
    VALIDATION_FAILURE = "validation_failure"
    POLICY_DENIAL = "policy_denial"
    APPROVAL_PENDING = "approval_pending"
    APPROVAL_DENIED = "approval_denied"
    APPROVAL_EXPIRED = "approval_expired"
    ADAPTER_FAILURE = "adapter_failure"
    EXECUTION_FAILURE = "execution_failure"
    OUTPUT_SCHEMA_VALIDATION_FAILURE = "output_schema_validation_failure"
    RUNTIME_TIMEOUT = "runtime_timeout"
    SCOPE_VIOLATION = "scope_violation"
    REDACTION_FAILURE = "redaction_failure"
    VERIFICATION_FAILURE = "verification_failure"
    INTERNAL_SYSTEM_FAILURE = "internal_system_failure"
