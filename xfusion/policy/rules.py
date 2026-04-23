from __future__ import annotations

from typing import Any

from xfusion.capabilities.registry import build_default_capability_registry
from xfusion.domain.enums import ApprovalMode, PolicyDecisionValue, RiskTier
from xfusion.domain.models.capability import CapabilityDefinition
from xfusion.domain.models.environment import EnvironmentState
from xfusion.domain.models.policy import PolicyDecision, StepRiskContract
from xfusion.policy.approval import stable_hash
from xfusion.policy.protected_paths import is_protected
from xfusion.policy.risk import (
    build_risk_contract,
    classify_risk_traits,
    evaluate_risk_policy,
)
from xfusion.security.secrets import is_secret_path


def _confirmation_type_for_mode(mode: ApprovalMode) -> str:
    if mode == ApprovalMode.ADMIN:
        return "admin"
    if mode == ApprovalMode.HUMAN:
        return "user"
    return "none"


def _decision(
    *,
    decision: PolicyDecisionValue,
    matched_rule_id: str,
    capability: CapabilityDefinition | None,
    risk_tier: RiskTier,
    approval_mode: ApprovalMode,
    reason: str,
    deny_code: str | None,
    reason_codes: list[str],
    risk_contract: StepRiskContract | dict[str, object] | None = None,
    constraints_applied: list[str] | None = None,
    extra_explainability: dict[str, Any] | None = None,
) -> PolicyDecision:
    risk_contract_payload_raw = (
        risk_contract.model_dump() if isinstance(risk_contract, StepRiskContract) else risk_contract
    )
    risk_contract_payload = (
        StepRiskContract.model_validate(risk_contract_payload_raw)
        if isinstance(risk_contract_payload_raw, dict)
        else risk_contract_payload_raw
    )
    return PolicyDecision(
        decision=decision,
        matched_rule_id=matched_rule_id,
        risk_tier=risk_tier,
        approval_mode=approval_mode,
        constraints_applied=constraints_applied or [],
        reason_codes=reason_codes,
        confirmation_type=_confirmation_type_for_mode(approval_mode),
        deny_code=deny_code,
        explainability_record={
            "capability": capability.name if capability else None,
            "capability_version": capability.version if capability else None,
            "matched_rule_id": matched_rule_id,
            "constraints_applied": constraints_applied or [],
            "approval_mode": approval_mode,
            "decision": decision,
            "reason_codes": reason_codes,
            "risk_contract": (risk_contract_payload.model_dump() if risk_contract_payload else {}),
            **(extra_explainability or {}),
        },
        reason_text=reason,
        reason=reason,
        risk_contract=risk_contract_payload,
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


def build_policy_snapshot_payload(
    *,
    capability_name: str,
    normalized_args: dict[str, object],
    argument_provenance: dict[str, str],
    decision: PolicyDecision,
    environment: EnvironmentState,
    step_binding: dict[str, object],
) -> dict[str, object]:
    """Return deterministic policy snapshot payload used for execute-time integrity checks."""
    return {
        "capability": capability_name,
        "normalized_args": normalized_args,
        "argument_provenance": argument_provenance,
        "decision": decision.decision.value,
        "matched_rule_id": decision.matched_rule_id,
        "risk_tier": decision.risk_tier.value,
        "approval_mode": decision.approval_mode.value,
        "confirmation_type": decision.confirmation_type,
        "deny_code": decision.deny_code,
        "reason_codes": list(decision.reason_codes),
        "risk_contract": decision.risk_contract.model_dump() if decision.risk_contract else {},
        "environment": environment.model_dump(mode="json"),
        "step_binding": step_binding,
    }


def build_policy_snapshot_hash(payload: dict[str, object]) -> str:
    return stable_hash(payload)


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

    This function is authoritative for allow/require_confirmation/deny decisions
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
            deny_code="invalid_policy_invocation",
            reason_codes=["invalid_policy_invocation", "deny_by_default"],
            risk_contract={
                "risk_level": "critical",
                "requires_confirmation": False,
                "confirmation_type": "none",
                "deny_code": "invalid_policy_invocation",
                "deny_reason_text": "Missing required capability name for policy evaluation.",
                "deny_reason": "Missing required capability name for policy evaluation.",
                "side_effects": [],
                "reversibility": "destructive",
                "privilege_required": False,
            },
        )
    if resolved_args is None:
        return _decision(
            decision=PolicyDecisionValue.DENY,
            matched_rule_id="default.invalid_invocation_contract",
            capability=None,
            risk_tier=RiskTier.TIER_3,
            approval_mode=ApprovalMode.DENY,
            reason="Missing required resolved args for policy evaluation.",
            deny_code="invalid_policy_invocation",
            reason_codes=["invalid_policy_invocation", "deny_by_default"],
            risk_contract={
                "risk_level": "critical",
                "requires_confirmation": False,
                "confirmation_type": "none",
                "deny_code": "invalid_policy_invocation",
                "deny_reason_text": "Missing required resolved args for policy evaluation.",
                "deny_reason": "Missing required resolved args for policy evaluation.",
                "side_effects": [],
                "reversibility": "destructive",
                "privilege_required": False,
            },
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
            deny_code="unknown_capability",
            reason_codes=["unknown_capability", "deny_by_default"],
            risk_contract={
                "risk_level": "critical",
                "requires_confirmation": False,
                "confirmation_type": "none",
                "deny_code": "unknown_capability",
                "deny_reason_text": f"Unknown capability '{name}' is denied by default.",
                "deny_reason": f"Unknown capability '{name}' is denied by default.",
                "side_effects": ["unknown_capability"],
                "reversibility": "destructive",
                "privilege_required": False,
            },
        )

    if actor_type not in capability.allowed_actor_types:
        return _decision(
            decision=PolicyDecisionValue.DENY,
            matched_rule_id="actor.denied",
            capability=capability,
            risk_tier=RiskTier.TIER_3,
            approval_mode=ApprovalMode.DENY,
            reason=f"Actor type '{actor_type}' is not allowed for capability '{name}'.",
            deny_code="actor_type_not_allowed",
            reason_codes=["actor_type_not_allowed"],
            risk_contract={
                "risk_level": "critical",
                "requires_confirmation": False,
                "confirmation_type": "none",
                "deny_code": "actor_type_not_allowed",
                "deny_reason_text": (
                    f"Actor type '{actor_type}' is not allowed for capability '{name}'."
                ),
                "deny_reason": (
                    f"Actor type '{actor_type}' is not allowed for capability '{name}'."
                ),
                "side_effects": [],
                "reversibility": "destructive",
                "privilege_required": False,
            },
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
                deny_code="secret_path",
                reason_codes=["secret_path", "secret_denied"],
                risk_contract={
                    "risk_level": "critical",
                    "requires_confirmation": False,
                    "confirmation_type": "none",
                    "deny_code": "secret_path",
                    "deny_reason_text": f"Path '{path}' is known secret material and is denied.",
                    "deny_reason": f"Path '{path}' is known secret material and is denied.",
                    "side_effects": ["secret_material_access"],
                    "reversibility": "destructive",
                    "privilege_required": False,
                },
            )
        if is_protected(path, environment.protected_paths) and not capability.is_read_only:
            return _decision(
                decision=PolicyDecisionValue.DENY,
                matched_rule_id="protected_path.deny_mutation",
                capability=capability,
                risk_tier=RiskTier.TIER_3,
                approval_mode=ApprovalMode.DENY,
                reason=f"Path '{path}' is protected and cannot be modified.",
                deny_code="protected_path",
                reason_codes=["protected_path", "scope_violation"],
                risk_contract={
                    "risk_level": "critical",
                    "requires_confirmation": False,
                    "confirmation_type": "none",
                    "deny_code": "protected_path",
                    "deny_reason_text": f"Path '{path}' is protected and cannot be modified.",
                    "deny_reason": f"Path '{path}' is protected and cannot be modified.",
                    "side_effects": ["filesystem_mutation", "data_destructive"],
                    "reversibility": "destructive",
                    "privilege_required": True,
                },
            )

    if target_scope != "explicit":
        scope_reason = (
            f"Capability '{name}' requires explicit target scope; received '{target_scope}'."
        )
        return _decision(
            decision=PolicyDecisionValue.DENY,
            matched_rule_id="scope.explicit_required",
            capability=capability,
            risk_tier=RiskTier.TIER_3,
            approval_mode=ApprovalMode.DENY,
            reason=scope_reason,
            deny_code="scope_not_explicit",
            reason_codes=["scope_not_explicit", "deny_by_default"],
            risk_contract={
                "risk_level": "critical",
                "requires_confirmation": False,
                "confirmation_type": "none",
                "deny_code": "scope_not_explicit",
                "deny_reason_text": scope_reason,
                "deny_reason": scope_reason,
                "side_effects": [],
                "reversibility": "destructive",
                "privilege_required": False,
            },
            extra_explainability={
                "target_scope": target_scope,
                "request_intent": request_intent,
                "argument_provenance": argument_provenance or {},
            },
        )

    if name == "plan.explain_action":
        path = str(args.get("path", "the requested path"))
        action = str(args.get("action", "action"))
        permission_reason = (
            f"Recursive {action} permission changes on protected path '{path}' are forbidden."
        )
        return _decision(
            decision=PolicyDecisionValue.DENY,
            matched_rule_id="protected_path.recursive_permission_change.deny",
            capability=capability,
            risk_tier=RiskTier.TIER_3,
            approval_mode=ApprovalMode.DENY,
            reason=permission_reason,
            deny_code="permission_change_forbidden",
            reason_codes=["protected_path", "permission_change_forbidden"],
            risk_contract={
                "risk_level": "critical",
                "requires_confirmation": False,
                "confirmation_type": "none",
                "deny_code": "permission_change_forbidden",
                "deny_reason_text": permission_reason,
                "deny_reason": permission_reason,
                "side_effects": ["filesystem_mutation", "data_destructive"],
                "reversibility": "destructive",
                "privilege_required": True,
            },
        )

    traits = classify_risk_traits(
        capability=capability,
        resolved_args=args,
        environment=environment,
    )
    risk_eval = evaluate_risk_policy(traits)
    deny_code = risk_eval.reason_codes[0] if risk_eval.effect == "deny" else None
    deny_reason_text = risk_eval.reason if risk_eval.effect == "deny" else None
    risk_contract = build_risk_contract(
        traits=traits,
        outcome=risk_eval,
        deny_code=deny_code,
        deny_reason_text=deny_reason_text,
    ).model_dump()

    decision_map = {
        "allow": PolicyDecisionValue.ALLOW,
        "require_confirmation": PolicyDecisionValue.REQUIRE_CONFIRMATION,
        "deny": PolicyDecisionValue.DENY,
    }
    tier_map = {
        "low": RiskTier.TIER_0,
        "medium": RiskTier.TIER_1,
        "high": RiskTier.TIER_2,
        "critical": RiskTier.TIER_3,
    }
    approval_mode = ApprovalMode.DENY
    if risk_eval.effect == "allow":
        approval_mode = ApprovalMode.AUTO
    elif risk_eval.effect == "require_confirmation":
        approval_mode = ApprovalMode.ADMIN if risk_eval.risk_level == "high" else ApprovalMode.HUMAN

    constraints = ["explicit_scope", "network_denied"]
    if risk_eval.effect == "require_confirmation":
        constraints.append("step_bound_typed_confirmation")
    if risk_eval.risk_level == "high":
        constraints.append("admin_confirmation_required")

    return _decision(
        decision=decision_map[risk_eval.effect],
        matched_rule_id=risk_eval.matched_rule_id,
        capability=capability,
        risk_tier=tier_map[risk_eval.risk_level],
        approval_mode=approval_mode,
        constraints_applied=constraints,
        reason=risk_eval.reason,
        deny_code=deny_code,
        reason_codes=list(risk_eval.reason_codes),
        risk_contract=risk_contract,
        extra_explainability={
            "argument_provenance": argument_provenance or {},
            "host_class": host_class,
            "target_scope": target_scope,
            "request_intent": request_intent,
            "command_family": traits.command_family,
            "risk_traits": {
                "read_only": traits.read_only,
                "mutation": traits.mutation,
                "cleanup_preview": traits.cleanup_preview,
                "privilege_required": traits.privilege_required,
                "filesystem_mutation": traits.filesystem_mutation,
                "process_control": traits.process_control,
                "network_or_system_config_change": traits.network_or_system_config_change,
                "data_destructive": traits.data_destructive,
                "broad_impact": traits.broad_impact,
                "unknown_risky_pattern": traits.unknown_risky_pattern,
            },
            "prior_approval_state": prior_approval_state or {},
            "time_quota_context": time_quota_context or {},
        },
    )
