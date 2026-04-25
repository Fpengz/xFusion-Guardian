from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from xfusion.domain.models.capability import CapabilityDefinition
from xfusion.domain.models.environment import EnvironmentState
from xfusion.domain.models.policy import StepRiskContract

PolicyEffect = Literal["allow", "require_confirmation", "deny"]


@dataclass(frozen=True)
class RiskTraits:
    """Deterministic traits extracted from capability+args for policy matching."""

    command_family: str
    read_only: bool
    mutation: bool
    cleanup_preview: bool
    privilege_required: bool
    filesystem_mutation: bool
    process_control: bool
    network_or_system_config_change: bool
    data_destructive: bool
    broad_impact: bool
    unknown_risky_pattern: bool


@dataclass(frozen=True)
class RiskPolicyOutcome:
    """Policy table result for one classified invocation."""

    matched_rule_id: str
    effect: PolicyEffect
    risk_level: Literal["low", "medium", "high", "critical"]
    reason: str
    reason_codes: tuple[str, ...]


@dataclass(frozen=True)
class RiskPolicyRule:
    """Explicit policy-table row for deterministic risk gating."""

    rule_id: str
    effect: PolicyEffect
    risk_level: Literal["low", "medium", "high", "critical"]
    reason: str
    reason_codes: tuple[str, ...]


RISK_POLICY_TABLE: tuple[RiskPolicyRule, ...] = (
    RiskPolicyRule(
        rule_id="risk.read_only.allow",
        effect="allow",
        risk_level="low",
        reason="Read-only inspection is allowed within explicit scope.",
        reason_codes=("read_only_allowed",),
    ),
    RiskPolicyRule(
        rule_id="risk.cleanup_preview.allow",
        effect="allow",
        risk_level="low",
        reason="Cleanup preview is read-only and bounded.",
        reason_codes=("preview_allowed",),
    ),
    RiskPolicyRule(
        rule_id="risk.unknown_pattern.deny",
        effect="deny",
        risk_level="critical",
        reason="Invocation arguments contain an unknown risky command pattern.",
        reason_codes=("unknown_risky_pattern", "deny_by_default"),
    ),
    RiskPolicyRule(
        rule_id="risk.broad_impact.deny",
        effect="deny",
        risk_level="critical",
        reason="Broad-impact destructive action is denied.",
        reason_codes=("broad_impact_destructive", "deny_by_default"),
    ),
    RiskPolicyRule(
        rule_id="risk.network_or_system_change.deny",
        effect="deny",
        risk_level="critical",
        reason=(
            "Network/system configuration mutations are denied unless "
            "explicitly approved by policy."
        ),
        reason_codes=("network_or_system_change", "deny_by_default"),
    ),
    RiskPolicyRule(
        rule_id="risk.destructive.confirm",
        effect="require_confirmation",
        risk_level="high",
        reason="Destructive mutation requires explicit admin confirmation.",
        reason_codes=("destructive_requires_admin_confirmation",),
    ),
    RiskPolicyRule(
        rule_id="risk.process_control.confirm",
        effect="require_confirmation",
        risk_level="high",
        reason="Process-control mutation requires admin confirmation.",
        reason_codes=("process_control_requires_admin_confirmation",),
    ),
    RiskPolicyRule(
        rule_id="risk.privileged_mutation.confirm",
        effect="require_confirmation",
        risk_level="medium",
        reason="Privileged bounded mutation requires explicit user confirmation.",
        reason_codes=("privileged_mutation_requires_user_confirmation",),
    ),
    RiskPolicyRule(
        rule_id="risk.filesystem_mutation.confirm",
        effect="require_confirmation",
        risk_level="medium",
        reason="Filesystem mutation requires explicit confirmation.",
        reason_codes=("filesystem_mutation_requires_confirmation",),
    ),
    RiskPolicyRule(
        rule_id="risk.unclassified_mutation.deny",
        effect="deny",
        risk_level="critical",
        reason="Unclassified mutation is denied by default.",
        reason_codes=("unclassified_mutation", "deny_by_default"),
    ),
)


def _is_truthy(value: object) -> bool:
    return value is True


def _detect_unknown_risky_pattern(args: dict[str, Any]) -> bool:
    risky_tokens = (
        "&&",
        "||",
        ";",
        "`",
        "$(",
        "rm -rf",
        "mkfs",
        "dd if=",
    )
    for value in args.values():
        if not isinstance(value, str):
            continue
        lowered = value.lower()
        if any(token in lowered for token in risky_tokens):
            return True
    return False


def classify_risk_traits(
    *,
    capability: CapabilityDefinition,
    resolved_args: dict[str, Any],
    environment: EnvironmentState,
) -> RiskTraits:
    """Classify deterministic risk traits from capability metadata and args."""
    del environment  # Reserved for future environment-sensitive classification.

    name = capability.name
    family = name.split(".", 1)[0]
    read_only = capability.is_read_only
    cleanup_preview = name == "cleanup.safe_disk_cleanup" and not _is_truthy(
        resolved_args.get("execute")
    )
    mutation = not read_only and not cleanup_preview

    process_control = name in {
        "process.kill",
        "system.service_restart",
        "system.service_stop",
        "system.service_start",
        "system.service_reload",
        "system.restart_failed_services",
        "process.terminate_by_name",
    }
    filesystem_mutation = name in {
        "cleanup.safe_disk_cleanup",
        "file.write_file",
        "file.delete",
        "file.move",
        "file.copy",
        "file.chmod",
        "file.chown",
        "file.append_file",
    }
    network_or_system_config_change = name in {
        "system.package_install",
        "system.firewall_update",
        "system.route_update",
        "system.config_write",
        "system.package_action",
        "system.upgrade",
    }
    privilege_required = name in {
        "process.kill",
        "user.create",
        "user.delete",
        "cleanup.safe_disk_cleanup",
        "system.service_start",
        "system.service_stop",
        "system.service_restart",
        "system.service_reload",
        "system.restart_failed_services",
        "file.chown",
        "system.package_action",
        "system.upgrade",
        "user.add_to_group",
        "user.remove_from_group",
    }

    data_destructive = False
    if name == "cleanup.safe_disk_cleanup" and _is_truthy(resolved_args.get("execute")):
        data_destructive = True
    if name == "process.kill" and str(resolved_args.get("signal", "TERM")).upper() in {
        "TERM",
        "KILL",
    }:
        data_destructive = True
    if name == "user.delete":
        data_destructive = True

    broad_impact = False
    all_paths: list[str] = []
    for key in ("path",):
        value = resolved_args.get(key)
        if isinstance(value, str):
            all_paths.append(value)
    approved_paths = resolved_args.get("approved_paths")
    if isinstance(approved_paths, list):
        all_paths.extend(str(path) for path in approved_paths)
    for path in all_paths:
        lowered = path.strip().lower()
        if lowered in {"/", "/*", "*", "/etc", "/usr", "/boot", "/var/lib"}:
            broad_impact = True

    unknown_risky_pattern = mutation and _detect_unknown_risky_pattern(resolved_args)

    return RiskTraits(
        command_family=family,
        read_only=read_only,
        mutation=mutation,
        cleanup_preview=cleanup_preview,
        privilege_required=privilege_required,
        filesystem_mutation=filesystem_mutation,
        process_control=process_control,
        network_or_system_config_change=network_or_system_config_change,
        data_destructive=data_destructive,
        broad_impact=broad_impact,
        unknown_risky_pattern=unknown_risky_pattern,
    )


def evaluate_risk_policy(traits: RiskTraits) -> RiskPolicyOutcome:
    """Evaluate deterministic risk policy table and return one explicit decision."""
    if traits.read_only:
        rule = RISK_POLICY_TABLE[0]
    elif traits.cleanup_preview:
        rule = RISK_POLICY_TABLE[1]
    elif traits.unknown_risky_pattern:
        rule = RISK_POLICY_TABLE[2]
    elif traits.broad_impact and traits.data_destructive:
        rule = RISK_POLICY_TABLE[3]
    elif traits.network_or_system_config_change:
        rule = RISK_POLICY_TABLE[4]
    elif traits.data_destructive:
        rule = RISK_POLICY_TABLE[5]
    elif traits.process_control:
        rule = RISK_POLICY_TABLE[6]
    elif traits.privilege_required:
        rule = RISK_POLICY_TABLE[7]
    elif traits.filesystem_mutation:
        rule = RISK_POLICY_TABLE[8]
    elif traits.mutation:
        rule = RISK_POLICY_TABLE[9]
    else:
        # Unreachable for registered capabilities; fail closed if reached.
        rule = RiskPolicyRule(
            rule_id="risk.fail_closed",
            effect="deny",
            risk_level="critical",
            reason="Unable to classify invocation risk deterministically.",
            reason_codes=("risk_classification_failed", "deny_by_default"),
        )

    return RiskPolicyOutcome(
        matched_rule_id=rule.rule_id,
        effect=rule.effect,
        risk_level=rule.risk_level,
        reason=rule.reason,
        reason_codes=rule.reason_codes,
    )


def build_risk_contract(
    *,
    traits: RiskTraits,
    outcome: RiskPolicyOutcome,
    deny_code: str | None = None,
    deny_reason_text: str | None = None,
) -> StepRiskContract:
    """Construct the normalized per-step risk contract for audit/execution gating."""
    side_effects: list[str] = []
    if traits.read_only or traits.cleanup_preview:
        side_effects.append("read_only_inspection")
    if traits.filesystem_mutation:
        side_effects.append("filesystem_mutation")
    if traits.process_control:
        side_effects.append("process_control")
    if traits.network_or_system_config_change:
        side_effects.append("network_or_system_config_change")
    if traits.data_destructive:
        side_effects.append("data_destructive")
    if traits.privilege_required:
        side_effects.append("privilege_escalation_required")
    if traits.unknown_risky_pattern:
        side_effects.append("unknown_risky_pattern")

    if traits.read_only or traits.cleanup_preview:
        reversibility = "reversible"
    elif traits.data_destructive:
        reversibility = "destructive"
    else:
        reversibility = "partially_reversible"

    confirmation_type = "none"
    if outcome.effect == "require_confirmation":
        confirmation_type = "admin" if outcome.risk_level == "high" else "user"

    return StepRiskContract(
        risk_level=outcome.risk_level,
        requires_confirmation=outcome.effect == "require_confirmation",
        confirmation_type=confirmation_type,
        deny_code=deny_code,
        deny_reason_text=deny_reason_text,
        deny_reason=deny_reason_text,
        side_effects=sorted(set(side_effects)),
        reversibility=reversibility,
        privilege_required=traits.privilege_required,
    )
