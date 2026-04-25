from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from xfusion.domain.enums import PolicyCategory
from xfusion.domain.models.execution_plan import PlanStep
from xfusion.policy.approval import stable_hash

_CATEGORY_RANK: dict[PolicyCategory, int] = {
    PolicyCategory.READ_ONLY: 0,
    PolicyCategory.WRITE_SAFE: 1,
    PolicyCategory.DESTRUCTIVE: 2,
    PolicyCategory.PRIVILEGED: 3,
    PolicyCategory.FORBIDDEN: 4,
}


class ImpactScope(BaseModel):
    """Structured scope described by the risk/impact agent."""

    model_config = ConfigDict(extra="forbid")

    filesystem: list[str] = Field(default_factory=list)
    processes: list[str] = Field(default_factory=list)
    network: bool = False
    privilege: bool = False
    global_impact: bool = False


class AgentRiskAssessment(BaseModel):
    """Agent-provided risk and consequence assessment.

    The assessment informs policy, but deterministic system guardrails may only
    preserve, escalate, or deny the category.
    """

    model_config = ConfigDict(extra="forbid")

    category: PolicyCategory
    confidence: float = Field(ge=0.0, le=1.0)
    impact_scope: ImpactScope = Field(default_factory=ImpactScope)
    expected_side_effects: list[str] = Field(default_factory=list)
    reversibility: str = "unknown"
    privilege_needed: bool = False
    confirmation_recommendation: str = "none"
    rationale: str = ""


class SystemRiskEnvelope(BaseModel):
    """Deterministic structural risk ceiling around agent classification."""

    model_config = ConfigDict(extra="forbid")

    agent_category: PolicyCategory
    final_category: PolicyCategory
    agent_rank: int
    final_rank: int
    escalated: bool = False
    denied: bool = False
    reason_codes: list[str] = Field(default_factory=list)


@dataclass(frozen=True)
class _StructuralFinding:
    category: PolicyCategory
    reason_code: str
    denied: bool = False


def _max_category(left: PolicyCategory, right: PolicyCategory) -> PolicyCategory:
    return left if _CATEGORY_RANK[left] >= _CATEGORY_RANK[right] else right


def _contains_wildcard(value: str) -> bool:
    return any(token in value for token in ("*", "?", "[", "]", "{", "}"))


def _structural_findings(
    *,
    command_argv: list[str],
    impact_scope: ImpactScope,
) -> list[_StructuralFinding]:
    findings: list[_StructuralFinding] = []
    filesystem_targets = set(impact_scope.filesystem)
    filesystem_targets.update(part for part in command_argv if part.startswith("/"))

    protected_targets = {"/", "/etc", "/usr", "/bin", "/sbin", "/boot", "/var/lib"}
    for path in filesystem_targets:
        normalized = path.rstrip("/") or "/"
        if normalized in protected_targets:
            findings.append(
                _StructuralFinding(
                    category=PolicyCategory.FORBIDDEN,
                    reason_code="protected_filesystem_target",
                    denied=True,
                )
            )

    command_name = command_argv[0] if command_argv else ""
    if command_name in {"sudo", "su", "doas"} or impact_scope.privilege:
        findings.append(
            _StructuralFinding(
                category=PolicyCategory.PRIVILEGED,
                reason_code="implicit_privilege_escalation",
            )
        )

    if command_name in {"rm", "unlink", "shred"} and any(
        _contains_wildcard(part) for part in command_argv[1:]
    ):
        findings.append(
            _StructuralFinding(
                category=PolicyCategory.FORBIDDEN,
                reason_code="wildcard_destructive_operation",
                denied=True,
            )
        )

    if command_name in {"kill", "pkill", "killall"}:
        process_targets = set(impact_scope.processes)
        process_targets.update(part for part in command_argv[1:] if part.isdigit())
        if "1" in process_targets or "kernel" in {target.lower() for target in process_targets}:
            findings.append(
                _StructuralFinding(
                    category=PolicyCategory.FORBIDDEN,
                    reason_code="critical_process_target",
                    denied=True,
                )
            )
        elif process_targets:
            findings.append(
                _StructuralFinding(
                    category=PolicyCategory.DESTRUCTIVE,
                    reason_code="process_control_impact",
                )
            )

    if impact_scope.network or impact_scope.global_impact:
        findings.append(
            _StructuralFinding(
                category=PolicyCategory.PRIVILEGED,
                reason_code="network_or_global_impact",
            )
        )

    return findings


def apply_system_risk_envelope(
    *,
    agent_assessment: AgentRiskAssessment,
    command_argv: list[str],
    impact_scope: ImpactScope | None = None,
) -> SystemRiskEnvelope:
    """Escalate or deny structurally unsafe actions without downgrading agents."""
    scope = impact_scope or agent_assessment.impact_scope
    final_category = agent_assessment.category
    reason_codes: list[str] = []
    denied = False

    if agent_assessment.category == PolicyCategory.FORBIDDEN:
        denied = True
        reason_codes.append("agent_forbidden_absolute_deny")

    for finding in _structural_findings(command_argv=command_argv, impact_scope=scope):
        final_category = _max_category(final_category, finding.category)
        reason_codes.append(finding.reason_code)
        denied = denied or finding.denied

    if final_category == PolicyCategory.FORBIDDEN:
        denied = True

    agent_rank = _CATEGORY_RANK[agent_assessment.category]
    final_rank = _CATEGORY_RANK[final_category]
    return SystemRiskEnvelope(
        agent_category=agent_assessment.category,
        final_category=final_category,
        agent_rank=agent_rank,
        final_rank=final_rank,
        escalated=final_rank > agent_rank,
        denied=denied,
        reason_codes=sorted(set(reason_codes)),
    )


def build_action_integrity_hash(step: PlanStep, *, resolved_args: dict[str, Any]) -> str:
    """Build a stable hash for the normalized action that will execute."""
    return stable_hash(
        {
            "execution_surface": step.execution_surface.value,
            "capability": step.capability,
            "template_id": step.resolution_record.get("template_id"),
            "raw_command_fingerprint": step.resolution_record.get("raw_command_fingerprint"),
            "resolved_args": resolved_args,
            "policy_category": step.final_risk_category or step.policy_category,
            "impact_scope": step.impact_scope,
        }
    )


def validate_execution_integrity(step: PlanStep) -> tuple[bool, str | None]:
    """Ensure an approved action is exactly the action being executed."""
    if (
        step.approved_action_hash
        and step.executed_action_hash
        and step.approved_action_hash != step.executed_action_hash
    ):
        return False, "approved_executed_action_hash_mismatch"
    return True, None


def normalize_command_fingerprint(command_argv: list[str]) -> str:
    """Return a privacy-preserving command shape for fallback hardening analytics."""
    normalized: list[str] = []
    for part in command_argv:
        if part.isdigit():
            normalized.append("{pid}")
        elif re.fullmatch(r"\d+(?:\.\d+)?", part):
            normalized.append("{number}")
        elif re.fullmatch(r"/[A-Za-z0-9._/\-]+", part):
            normalized.append("{path}")
        else:
            normalized.append(part)
    return " ".join(normalized)
