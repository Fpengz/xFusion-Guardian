from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from xfusion.domain.enums import ReasoningRole, RiskTier

ROLE_ALLOWED_PROPOSALS: dict[ReasoningRole, tuple[str, ...]] = {
    ReasoningRole.SUPERVISOR: ("intent", "coordination", "clarification"),
    ReasoningRole.OBSERVATION: ("tier_0_capability", "missing_evidence"),
    ReasoningRole.DIAGNOSIS: ("hypothesis", "confidence", "missing_evidence"),
    ReasoningRole.PLANNING: ("workflow_dag", "verification_strategy"),
    ReasoningRole.VERIFICATION: ("verification_outcome", "repair_proposal"),
    ReasoningRole.EXPLANATION: ("audit_summary", "safe_next_step"),
}

ROLE_RESPONSIBILITIES: dict[ReasoningRole, str] = {
    ReasoningRole.SUPERVISOR: (
        "Interpret user intent, coordinate role outputs, and request clarification."
    ),
    ReasoningRole.OBSERVATION: (
        "Propose bounded read-only Tier 0 evidence-gathering capabilities."
    ),
    ReasoningRole.DIAGNOSIS: (
        "Produce advisory hypotheses from typed observations without changing authority."
    ),
    ReasoningRole.PLANNING: (
        "Draft typed workflow DAGs with explicit dependencies, references, and verification."
    ),
    ReasoningRole.VERIFICATION: (
        "Evaluate redacted execution evidence and propose non-authoritative repair ideas."
    ),
    ReasoningRole.EXPLANATION: ("Summarize authoritative audited state and safe next steps."),
}

PROHIBITED_ROLE_AUTHORITIES = frozenset(
    {
        "execute",
        "authorize",
        "approve",
        "bypass_policy",
        "fabricate_output",
        "consume_unredacted_secret",
        "alter_audit",
    }
)


class RoleContract(BaseModel):
    """Non-authoritative reasoning-role boundary for v0.2."""

    model_config = ConfigDict(extra="forbid")

    role: ReasoningRole
    responsibility: str
    allowed_proposal_types: tuple[str, ...]
    prohibited_authorities: tuple[str, ...]
    max_steps: int = Field(ge=1, le=20)
    max_tokens_hint: int = Field(ge=128, le=16_000)
    authoritative: bool = False


class RoleProposal(BaseModel):
    """Typed non-authoritative proposal emitted by one reasoning role."""

    model_config = ConfigDict(extra="forbid")

    role: ReasoningRole
    proposal_type: str = Field(min_length=1)
    payload: dict[str, Any] = Field(default_factory=dict)
    requested_authority: list[str] = Field(default_factory=list)
    consumes_redacted_inputs_only: bool = True


class RoleProposalValidationResult(BaseModel):
    """Deterministic result for role boundary checks."""

    model_config = ConfigDict(extra="forbid")

    valid: bool
    errors: list[str] = Field(default_factory=list)


def build_default_role_contracts() -> dict[ReasoningRole, RoleContract]:
    """Return explicit role contracts; deterministic infrastructure remains authoritative."""
    budgets = {
        ReasoningRole.SUPERVISOR: (6, 2000),
        ReasoningRole.OBSERVATION: (8, 1500),
        ReasoningRole.DIAGNOSIS: (6, 1500),
        ReasoningRole.PLANNING: (10, 2500),
        ReasoningRole.VERIFICATION: (6, 1500),
        ReasoningRole.EXPLANATION: (4, 1200),
    }
    return {
        role: RoleContract(
            role=role,
            responsibility=ROLE_RESPONSIBILITIES[role],
            allowed_proposal_types=ROLE_ALLOWED_PROPOSALS[role],
            prohibited_authorities=tuple(sorted(PROHIBITED_ROLE_AUTHORITIES)),
            max_steps=budgets[role][0],
            max_tokens_hint=budgets[role][1],
            authoritative=False,
        )
        for role in ReasoningRole
    }


def validate_role_proposal(
    proposal: RoleProposal,
    *,
    contracts: dict[ReasoningRole, RoleContract] | None = None,
) -> RoleProposalValidationResult:
    """Validate a reasoning proposal without granting any execution authority."""
    role_contracts = contracts or build_default_role_contracts()
    contract = role_contracts[proposal.role]
    errors: list[str] = []

    if contract.authoritative:
        errors.append(f"Role '{proposal.role}' must be non-authoritative.")
    if proposal.proposal_type not in contract.allowed_proposal_types:
        errors.append(
            f"Proposal type '{proposal.proposal_type}' is not allowed for role '{proposal.role}'."
        )

    requested = {item.lower() for item in proposal.requested_authority}
    prohibited = requested & PROHIBITED_ROLE_AUTHORITIES
    if prohibited:
        errors.append(
            f"Reasoning roles are non-authoritative and cannot request {sorted(prohibited)!r}."
        )

    if proposal.role == ReasoningRole.OBSERVATION:
        risk_tier = proposal.payload.get("risk_tier")
        if risk_tier is not None and risk_tier != RiskTier.TIER_0.value:
            errors.append("Observation proposals may only target Tier 0 capabilities.")
    if proposal.role == ReasoningRole.VERIFICATION and not proposal.consumes_redacted_inputs_only:
        errors.append("Verification role proposals may consume only redacted inputs.")
    if proposal.role == ReasoningRole.EXPLANATION and not proposal.consumes_redacted_inputs_only:
        errors.append("Explanation role proposals may consume only audited redacted inputs.")

    return RoleProposalValidationResult(valid=not errors, errors=errors)
