from __future__ import annotations

from typing import Any

from xfusion.capabilities.registry import build_default_capability_registry
from xfusion.domain.enums import ApprovalMode, PolicyDecisionValue, RiskTier
from xfusion.domain.models.capability import CapabilityDefinition
from xfusion.domain.models.environment import EnvironmentState
from xfusion.domain.models.policy import PolicyDecision
from xfusion.policy.protected_paths import is_protected
from xfusion.security.secrets import is_secret_path


def _decision(
    *,
    decision: PolicyDecisionValue,
    matched_rule_id: str,
    capability: CapabilityDefinition | None,
    risk_tier: RiskTier,
    approval_mode: ApprovalMode,
    reason: str,
    reason_codes: list[str],
    constraints_applied: list[str] | None = None,
    extra_explainability: dict[str, Any] | None = None,
) -> PolicyDecision:
    return PolicyDecision(
        decision=decision,
        matched_rule_id=matched_rule_id,
        risk_tier=risk_tier,
        approval_mode=approval_mode,
        constraints_applied=constraints_applied or [],
        reason_codes=reason_codes,
        explainability_record={
            "capability": capability.name if capability else None,
            "capability_version": capability.version if capability else None,
            "matched_rule_id": matched_rule_id,
            "constraints_applied": constraints_applied or [],
            "approval_mode": approval_mode,
            "decision": decision,
            "reason_codes": reason_codes,
            **(extra_explainability or {}),
        },
        reason=reason,
    )


def _target_paths(args: dict[str, object]) -> list[str]:
    paths: list[str] = []
    if isinstance(args.get("path"), str):
        paths.append(str(args["path"]))
    approved_paths = args.get("approved_paths")
    if isinstance(approved_paths, list):
        paths.extend(str(path) for path in approved_paths)
    raw_paths = args.get("paths")
    if isinstance(raw_paths, list):
        paths.extend(str(path) for path in raw_paths)
    return paths


def evaluate_policy(
    *,
    capability_name: str | None = None,
    resolved_args: dict[str, object] | None = None,
    argument_provenance: dict[str, str] | None = None,
    environment: EnvironmentState,
    actor_type: str = "assistant",
    host_class: str = "production",
    target_scope: str = "explicit",
    request_intent: str = "operation",
    prior_approval_state: dict[str, object] | None = None,
    time_quota_context: dict[str, object] | None = None,
) -> PolicyDecision:
    """Return the v0.2 deterministic policy decision for a capability invocation.

    This function is authoritative for allow/require_approval/deny decisions
    and defaults to deny when invocation inputs or matching rules are unclear.
    """
    if not capability_name:
        return _decision(
            decision=PolicyDecisionValue.DENY,
            matched_rule_id="default.invalid_invocation_contract",
            capability=None,
            risk_tier=RiskTier.TIER_3,
            approval_mode=ApprovalMode.DENY,
            reason="Missing required capability name for policy evaluation.",
            reason_codes=["invalid_policy_invocation", "deny_by_default"],
        )
    if resolved_args is None:
        return _decision(
            decision=PolicyDecisionValue.DENY,
            matched_rule_id="default.invalid_invocation_contract",
            capability=None,
            risk_tier=RiskTier.TIER_3,
            approval_mode=ApprovalMode.DENY,
            reason="Missing required resolved args for policy evaluation.",
            reason_codes=["invalid_policy_invocation", "deny_by_default"],
        )

    name = capability_name
    args = resolved_args
    registry = build_default_capability_registry()
    capability = registry.get(name)

    if capability is None:
        return _decision(
            decision=PolicyDecisionValue.DENY,
            matched_rule_id="default.deny_unknown_capability",
            capability=None,
            risk_tier=RiskTier.TIER_3,
            approval_mode=ApprovalMode.DENY,
            reason=f"Unknown capability '{name}' is denied by default.",
            reason_codes=["unknown_capability", "deny_by_default"],
        )

    if actor_type not in capability.allowed_actor_types:
        return _decision(
            decision=PolicyDecisionValue.DENY,
            matched_rule_id="actor.denied",
            capability=capability,
            risk_tier=RiskTier.TIER_3,
            approval_mode=ApprovalMode.DENY,
            reason=f"Actor type '{actor_type}' is not allowed for capability '{name}'.",
            reason_codes=["actor_type_not_allowed"],
        )

    for path in _target_paths(args):
        if is_secret_path(path):
            return _decision(
                decision=PolicyDecisionValue.DENY,
                matched_rule_id="secret_path.deny",
                capability=capability,
                risk_tier=RiskTier.TIER_3,
                approval_mode=ApprovalMode.DENY,
                reason=f"Path '{path}' is known secret material and is denied.",
                reason_codes=["secret_path", "secret_denied"],
            )
        if is_protected(path, environment.protected_paths) and not capability.is_read_only:
            return _decision(
                decision=PolicyDecisionValue.DENY,
                matched_rule_id="protected_path.deny_mutation",
                capability=capability,
                risk_tier=RiskTier.TIER_3,
                approval_mode=ApprovalMode.DENY,
                reason=f"Path '{path}' is protected and cannot be modified.",
                reason_codes=["protected_path", "scope_violation"],
            )

    if target_scope != "explicit":
        return _decision(
            decision=PolicyDecisionValue.DENY,
            matched_rule_id="scope.explicit_required",
            capability=capability,
            risk_tier=RiskTier.TIER_3,
            approval_mode=ApprovalMode.DENY,
            reason=(
                f"Capability '{name}' requires explicit target scope; received '{target_scope}'."
            ),
            reason_codes=["scope_not_explicit", "deny_by_default"],
            extra_explainability={
                "target_scope": target_scope,
                "request_intent": request_intent,
                "argument_provenance": argument_provenance or {},
            },
        )

    if name == "plan.explain_action":
        path = str(args.get("path", "the requested path"))
        action = str(args.get("action", "action"))
        return _decision(
            decision=PolicyDecisionValue.DENY,
            matched_rule_id="protected_path.recursive_permission_change.deny",
            capability=capability,
            risk_tier=RiskTier.TIER_3,
            approval_mode=ApprovalMode.DENY,
            reason=(
                f"Recursive {action} permission changes on protected path '{path}' are forbidden."
            ),
            reason_codes=["protected_path", "permission_change_forbidden"],
        )

    if capability.risk_tier == RiskTier.TIER_3 or capability.approval_mode == ApprovalMode.DENY:
        return _decision(
            decision=PolicyDecisionValue.DENY,
            matched_rule_id="tier3.deny",
            capability=capability,
            risk_tier=RiskTier.TIER_3,
            approval_mode=ApprovalMode.DENY,
            reason=f"Capability '{name}' is prohibited or broad impact.",
            reason_codes=["tier_3_denied"],
        )

    if capability.risk_tier == RiskTier.TIER_0 and capability.is_read_only:
        return _decision(
            decision=PolicyDecisionValue.ALLOW,
            matched_rule_id="tier0.read_only.explicit_scope.allow",
            capability=capability,
            risk_tier=RiskTier.TIER_0,
            approval_mode=ApprovalMode.AUTO,
            constraints_applied=["explicit_scope", "read_only", "network_denied"],
            reason="Tier 0 read-only capability is allowed within explicit scope.",
            reason_codes=["tier_0_read_only_allowed"],
            extra_explainability={
                "argument_provenance": argument_provenance or {},
                "host_class": host_class,
                "target_scope": target_scope,
                "request_intent": request_intent,
            },
        )

    if capability.risk_tier == RiskTier.TIER_1:
        if name == "cleanup.safe_disk_cleanup" and args.get("execute") is not True:
            return _decision(
                decision=PolicyDecisionValue.ALLOW,
                matched_rule_id="tier1.cleanup_preview.allow",
                capability=capability,
                risk_tier=RiskTier.TIER_0,
                approval_mode=ApprovalMode.AUTO,
                constraints_applied=["preview_only", "bounded_candidates", "network_denied"],
                reason="Cleanup preview is read-only and bounded to approved candidates.",
                reason_codes=["preview_allowed"],
            )
        return _decision(
            decision=PolicyDecisionValue.REQUIRE_APPROVAL,
            matched_rule_id="tier1.mutation.human_approval",
            capability=capability,
            risk_tier=RiskTier.TIER_1,
            approval_mode=ApprovalMode.HUMAN,
            constraints_applied=["explicit_target", "human_approval_required", "network_denied"],
            reason=f"Capability '{name}' is a bounded mutation and requires human approval.",
            reason_codes=["tier_1_requires_human_approval"],
            extra_explainability={
                "prior_approval_state": prior_approval_state or {},
                "time_quota_context": time_quota_context or {},
            },
        )

    if capability.risk_tier == RiskTier.TIER_2:
        return _decision(
            decision=PolicyDecisionValue.REQUIRE_APPROVAL,
            matched_rule_id="tier2.mutation.admin_approval",
            capability=capability,
            risk_tier=RiskTier.TIER_2,
            approval_mode=ApprovalMode.ADMIN,
            constraints_applied=["admin_approval_required", "explicit_scope"],
            reason=f"Capability '{name}' is high risk and requires admin approval.",
            reason_codes=["tier_2_requires_admin_approval"],
        )

    return _decision(
        decision=PolicyDecisionValue.DENY,
        matched_rule_id="default.fail_closed",
        capability=capability,
        risk_tier=RiskTier.TIER_3,
        approval_mode=ApprovalMode.DENY,
        reason=f"No exact policy rule matched capability '{name}'.",
        reason_codes=["no_exact_rule", "deny_by_default"],
    )
