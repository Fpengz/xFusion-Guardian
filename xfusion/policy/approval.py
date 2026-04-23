from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

from xfusion.domain.enums import ApprovalMode, RiskTier
from xfusion.domain.models.approval import ApprovalRecord, PreviewPayload
from xfusion.domain.models.capability import CapabilityDefinition
from xfusion.domain.models.execution_plan import ExecutionPlan, PlanStep


def canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)


def stable_hash(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def build_argument_provenance(args: dict[str, Any]) -> dict[str, str]:
    provenance: dict[str, str] = {}
    for key, value in args.items():
        if isinstance(value, str) and value.startswith("$steps."):
            provenance[key] = f"reference:{value}"
        else:
            provenance[key] = "literal_or_validated_user_input"
    return provenance


def build_referenced_output_fingerprints(
    args: dict[str, Any],
    authorized_outputs: dict[str, dict[str, Any]],
) -> dict[str, str]:
    fingerprints: dict[str, str] = {}
    for step_id, output in authorized_outputs.items():
        if f"$steps.{step_id}.outputs." in canonical_json(args):
            fingerprints[step_id] = stable_hash(output)
    return fingerprints


def build_action_fingerprint(
    *,
    capability: CapabilityDefinition,
    normalized_args: dict[str, Any],
    argument_provenance: dict[str, str],
    target_context: dict[str, Any],
    approval_mode: ApprovalMode,
    risk_tier: RiskTier,
    referenced_output_fingerprints: dict[str, str],
    grouped_mutations: list[str] | None = None,
) -> str:
    payload = {
        "capability": capability.name,
        "capability_version": capability.version,
        "adapter_id": capability.adapter_id,
        "normalized_args": normalized_args,
        "argument_provenance": argument_provenance,
        "target_context": target_context,
        "approval_mode": approval_mode,
        "risk_tier": risk_tier,
        "referenced_output_fingerprints": referenced_output_fingerprints,
        "grouped_mutations": grouped_mutations or [capability.name],
    }
    return stable_hash(payload)


def build_preview_payload(
    *,
    capability: CapabilityDefinition,
    step: PlanStep,
    normalized_args: dict[str, Any],
    argument_provenance: dict[str, str],
    approval_mode: ApprovalMode,
    expires_at: datetime,
) -> PreviewPayload:
    impacted_target = str(
        normalized_args.get("path")
        or normalized_args.get("pid")
        or normalized_args.get("service")
        or normalized_args.get("username")
        or capability.object
    )
    action_summary = (
        step.preview_summary or step.justification or f"{capability.verb} {capability.object}"
    )
    return PreviewPayload(
        impacted_target=impacted_target,
        action_summary=action_summary,
        reversibility_estimate="bounded" if capability.risk_tier == RiskTier.TIER_1 else "limited",
        expected_blast_radius="single declared target/scope",
        capability=capability.name,
        normalized_args=normalized_args,
        argument_provenance_summary=argument_provenance,
        rollback_notes=step.fallback_action or None,
        approval_mode=approval_mode,
        expiry=expires_at,
    )


def create_approval_record(
    *,
    plan: ExecutionPlan,
    step: PlanStep,
    capability: CapabilityDefinition,
    normalized_args: dict[str, Any],
    target_context: dict[str, Any],
    approval_mode: ApprovalMode,
    risk_tier: RiskTier,
    authorized_outputs: dict[str, dict[str, Any]],
    ttl_minutes: int = 10,
) -> ApprovalRecord:
    expires_at = datetime.now(UTC) + timedelta(minutes=ttl_minutes)
    provenance = build_argument_provenance(step.args)
    referenced_output_fingerprints = build_referenced_output_fingerprints(
        step.args, authorized_outputs
    )
    fingerprint = build_action_fingerprint(
        capability=capability,
        normalized_args=normalized_args,
        argument_provenance=provenance,
        target_context=target_context,
        approval_mode=approval_mode,
        risk_tier=risk_tier,
        referenced_output_fingerprints=referenced_output_fingerprints,
    )
    approval_id = f"apr_{uuid4().hex[:12]}"
    phrase = f"APPROVE {approval_id} {fingerprint[:12]}"
    preview = build_preview_payload(
        capability=capability,
        step=step,
        normalized_args=normalized_args,
        argument_provenance=provenance,
        approval_mode=approval_mode,
        expires_at=expires_at,
    )
    return ApprovalRecord(
        approval_id=approval_id,
        plan_id=plan.plan_id,
        step_id=step.step_id,
        normalized_capability_set=[capability.name],
        target_context=target_context,
        action_fingerprint=fingerprint,
        referenced_output_fingerprints=referenced_output_fingerprints,
        approval_mode=approval_mode,
        risk_tier=risk_tier,
        adapter_id=capability.adapter_id,
        capability_version=capability.version,
        preview=preview,
        typed_confirmation_phrase=phrase,
        expires_at=expires_at,
    )


def validate_approval_for_invocation(
    *,
    approval: ApprovalRecord,
    capability: CapabilityDefinition,
    normalized_args: dict[str, Any],
    target_context: dict[str, Any],
    approval_mode: ApprovalMode,
    risk_tier: RiskTier,
    argument_provenance: dict[str, str],
    referenced_output_fingerprints: dict[str, str],
) -> tuple[bool, str]:
    if not approval.is_approved:
        return False, "approval_not_approved"
    if approval.is_expired():
        return False, "approval_expired"
    current = build_action_fingerprint(
        capability=capability,
        normalized_args=normalized_args,
        argument_provenance=argument_provenance,
        target_context=target_context,
        approval_mode=approval_mode,
        risk_tier=risk_tier,
        referenced_output_fingerprints=referenced_output_fingerprints,
    )
    if current != approval.action_fingerprint:
        return False, "material_change"
    return True, "approval_valid"
