from __future__ import annotations

from typing import cast

import pytest
from pydantic import ValidationError

from xfusion.capabilities.default_templates import build_default_templates
from xfusion.capabilities.registry import build_default_capability_registry
from xfusion.capabilities.templates import TemplateEngine
from xfusion.domain.enums import ExecutionSurface, InteractionState, PolicyCategory, StepStatus
from xfusion.domain.models.environment import EnvironmentState
from xfusion.domain.models.execution_plan import ExecutionPlan, PlanStep
from xfusion.execution.resolver import ExecutionTier, HybridExecutionResolver
from xfusion.graph.auditing import log_graph_event
from xfusion.graph.state import AgentGraphState
from xfusion.policy.envelope import (
    AgentRiskAssessment,
    ImpactScope,
    apply_system_risk_envelope,
    normalize_command_fingerprint,
    validate_execution_integrity,
)
from xfusion.policy.rules import evaluate_policy


def test_system_risk_envelope_escalates_underclassified_agent_assessment() -> None:
    agent_assessment = AgentRiskAssessment(
        category=PolicyCategory.READ_ONLY,
        confidence=0.91,
        impact_scope=ImpactScope(filesystem=["/etc"], global_impact=False),
        rationale="Agent believed this was inspection only.",
    )

    envelope = apply_system_risk_envelope(
        agent_assessment=agent_assessment,
        command_argv=["rm", "-rf", "/etc"],
        impact_scope=agent_assessment.impact_scope,
    )

    assert envelope.final_category == PolicyCategory.FORBIDDEN
    assert envelope.agent_category == PolicyCategory.READ_ONLY
    assert envelope.escalated is True
    assert envelope.denied is True
    assert envelope.final_rank >= envelope.agent_rank
    assert "protected_filesystem_target" in envelope.reason_codes


def test_resolver_enforces_capability_over_agent_requested_shell() -> None:
    resolver = HybridExecutionResolver(
        capability_registry=build_default_capability_registry(),
        template_engine=TemplateEngine(build_default_templates()),
    )

    result = resolver.resolve(
        intent="check disk usage",
        llm_selected_tool={
            "type": "shell",
            "command": "df -h /",
            "applicable_capabilities": [{"name": "disk.check_usage", "arguments": {"path": "/"}}],
        },
    )

    assert result.success is True
    assert result.tier == ExecutionTier.TIER_1_CAPABILITY
    assert result.capability_name == "disk.check_usage"
    assert result.metadata["surface_order_enforced"] is True


def test_resolver_enforces_template_over_agent_requested_shell() -> None:
    resolver = HybridExecutionResolver(
        capability_registry=build_default_capability_registry(),
        template_engine=TemplateEngine(build_default_templates()),
    )

    result = resolver.resolve(
        intent="tail a log file",
        llm_selected_tool={
            "type": "shell",
            "command": "tail -n 25 /tmp/app.log",
            "applicable_templates": [
                {
                    "name": "logs.tail",
                    "arguments": {"path": "/tmp/app.log", "lines": 25},
                }
            ],
        },
    )

    assert result.success is True
    assert result.tier == ExecutionTier.TIER_2_TEMPLATE
    assert result.template_name == "logs.tail"
    assert result.metadata["surface_order_enforced"] is True


def test_default_templates_are_argv_safe_for_restricted_runtime() -> None:
    unsafe_tokens = {"|", ">", ">>", "<", "&&", "||", ";", "$(", "`"}
    offenders = [
        template.name
        for template in build_default_templates()
        if template.enabled
        for token in unsafe_tokens
        if token in template.command
    ]

    assert offenders == []


def test_template_engine_rejects_rendered_shell_metacharacters() -> None:
    engine = TemplateEngine(build_default_templates())

    result = engine.validate_parameters("logs.search", {"path": "/tmp/app.log", "pattern": "*"})

    assert result.valid is False
    assert "shell metacharacter" in "; ".join(result.errors)


def test_shell_fallback_requires_explicit_reason() -> None:
    resolver = HybridExecutionResolver(
        capability_registry=build_default_capability_registry(),
        template_engine=TemplateEngine(build_default_templates()),
    )

    result = resolver.resolve(
        intent="show unusual kernel detail",
        llm_selected_tool={"type": "shell", "command": "uname -a"},
    )

    assert result.success is False
    assert result.error == "Restricted shell fallback requires a structured fallback reason"


def test_shell_fallback_records_fingerprint_and_reason_metadata() -> None:
    resolver = HybridExecutionResolver(
        capability_registry=build_default_capability_registry(),
        template_engine=TemplateEngine(build_default_templates()),
    )

    result = resolver.resolve(
        intent="inspect a platform detail not covered by capabilities or templates",
        llm_selected_tool={
            "type": "shell",
            "command": "uname -a",
            "fallback_reason": {
                "no_capability": True,
                "no_template": True,
                "diagnostic_need": "kernel release inspection",
            },
        },
    )

    assert result.success is True
    assert result.tier == ExecutionTier.TIER_3_RESTRICTED_SHELL
    assert result.metadata["fallback_reason"]["diagnostic_need"] == "kernel release inspection"
    assert result.metadata["raw_command_fingerprint"] == "uname -a"


def test_forbidden_agent_assessment_is_absolute_deny() -> None:
    assessment = AgentRiskAssessment(
        category=PolicyCategory.FORBIDDEN,
        confidence=0.99,
        impact_scope=ImpactScope(global_impact=True),
        rationale="Agent identified a forbidden action.",
    )

    envelope = apply_system_risk_envelope(
        agent_assessment=assessment,
        command_argv=["echo", "noop"],
        impact_scope=assessment.impact_scope,
    )

    assert envelope.final_category == PolicyCategory.FORBIDDEN
    assert envelope.denied is True
    assert "agent_forbidden_absolute_deny" in envelope.reason_codes


def test_execution_integrity_requires_approved_hash_to_match_executed_hash() -> None:
    step = PlanStep(
        step_id="kill",
        capability="process.kill",
        args={"pid": 1234, "signal": "TERM"},
        execution_surface=ExecutionSurface.CAPABILITY,
        policy_category=PolicyCategory.DESTRUCTIVE,
        planned_action_hash="same",
        approved_action_hash="same",
        executed_action_hash="different",
    )

    valid, reason = validate_execution_integrity(step)

    assert valid is False
    assert reason == "approved_executed_action_hash_mismatch"


def test_normalized_command_fingerprint_generalizes_repeated_fallback_usage() -> None:
    assert normalize_command_fingerprint(["kill", "-9", "1234"]) == "kill -9 {pid}"
    assert normalize_command_fingerprint(["kill", "-9", "5678"]) == "kill -9 {pid}"


def test_audit_record_includes_hybrid_execution_surface_and_integrity_fields() -> None:
    step = PlanStep(
        step_id="inspect",
        capability="disk.check_usage",
        args={"path": "/"},
        execution_surface=ExecutionSurface.CAPABILITY,
        policy_category=PolicyCategory.READ_ONLY,
        final_risk_category=PolicyCategory.READ_ONLY,
        impact_scope={"filesystem": ["/"]},
        agent_risk_assessment={"category": "read_only", "confidence": 0.88},
        system_risk_envelope={"final_category": "read_only", "denied": False},
        resolution_record={"selected_by": "Planner_Resolver_Agent"},
        intent_hash="intent",
        planned_action_hash="planned",
        approved_action_hash="planned",
        executed_action_hash="planned",
        status=StepStatus.SUCCESS,
    )
    plan = ExecutionPlan(
        plan_id="audit-v0242",
        goal="check disk",
        language="en",
        interaction_state=InteractionState.COMPLETED,
        steps=[step],
        status="completed",
    )
    state = AgentGraphState(
        user_input="check disk",
        environment=EnvironmentState(),
        language="en",
        plan=plan,
        current_step_id=None,
        policy_decision=None,
        verification_result=None,
        last_tool_output=None,
        step_outputs={"inspect": {"ok": True}},
        authorized_step_outputs={},
        pending_confirmation_phrase=None,
        response="",
        audit_records=[],
    )

    log_graph_event(state, step=step, status="success", summary="ok")

    record = state.audit_records[-1]
    assert record["execution_surface"] == "capability"
    assert record["policy_category"] == "read_only"
    assert record["final_risk_category"] == "read_only"
    assert record["impact_scope"] == {"filesystem": ["/"]}
    integrity_hashes = cast(dict[str, object], record["integrity_hashes"])
    assert isinstance(integrity_hashes, dict)
    assert integrity_hashes["approved_action_hash"] == "planned"
    assert record["resolution_record"] == {"selected_by": "Planner_Resolver_Agent"}


def test_policy_decision_exposes_execution_surface_and_policy_category() -> None:
    decision = evaluate_policy(
        capability_name="disk.check_usage",
        resolved_args={"path": "/"},
        argument_provenance={"path": "literal_or_validated_user_input"},
        environment=EnvironmentState(),
    )

    assert decision.execution_surface == ExecutionSurface.CAPABILITY
    assert decision.policy_category == PolicyCategory.READ_ONLY


def test_malformed_agent_risk_assessment_is_rejected_fail_closed() -> None:
    with pytest.raises(ValidationError):
        AgentRiskAssessment.model_validate(
            {"category": "read_only", "confidence": 2.0, "unexpected": "ignored-by-agent"}
        )
