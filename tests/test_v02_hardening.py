from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from xfusion.capabilities.registry import CapabilityRegistry, build_default_capability_registry
from xfusion.capabilities.schema import SUPPORTED_SCHEMA_KEYWORDS, validate_schema_value
from xfusion.domain.enums import (
    ApprovalMode,
    InteractionState,
    PolicyDecisionValue,
    ReasoningRole,
    RiskTier,
    StepStatus,
)
from xfusion.domain.models.capability import (
    CapabilityDefinition,
    CapabilityPrompt,
    RuntimeConstraints,
)
from xfusion.domain.models.environment import EnvironmentState
from xfusion.domain.models.execution_plan import ExecutionPlan, PlanStep
from xfusion.execution.command_runner import CommandResult, CommandRunner
from xfusion.execution.runtime import ControlledAdapterRuntime
from xfusion.graph.wiring import build_agent_graph
from xfusion.planning.reference_resolver import resolve_args
from xfusion.planning.validator import validate_plan
from xfusion.policy.rules import evaluate_policy
from xfusion.roles.contracts import RoleProposal, validate_role_proposal
from xfusion.tools.base import ToolOutput
from xfusion.tools.process import ProcessTools
from xfusion.tools.system import SystemTools

SECRET = "password=supersecret token=abcdef1234567890"


class RaisingRegistry:
    def execute(self, name: str, args: dict[str, object]) -> ToolOutput:
        del args
        raise RuntimeError(f"adapter blew up with {SECRET}")


class TimeoutRegistry:
    def __init__(self) -> None:
        self.executed_tools: list[str] = []

    def execute(self, name: str, args: dict[str, object]) -> ToolOutput:
        del args
        self.executed_tools.append(name)
        raise TimeoutError(f"runtime exceeded limit while handling {SECRET}")


class BrokenReturnRegistry:
    def __init__(self) -> None:
        self.executed_tools: list[str] = []

    def execute(self, name: str, args: dict[str, object]) -> object:
        self.executed_tools.append(name)
        return object()


class OutputRegistry:
    def __init__(self, outputs: dict[str, dict[str, object]]) -> None:
        self.outputs = outputs
        self.executed_tools: list[str] = []

    def execute(self, name: str, args: dict[str, object]) -> ToolOutput:
        self.executed_tools.append(name)
        return ToolOutput(summary="adapter returned test output", data=self.outputs[name])


class FakeRunner(CommandRunner):
    def __init__(self) -> None:
        self.calls: list[list[str]] = []

    def run(self, command: list[str], **kwargs: object) -> CommandResult:
        self.calls.append(command)
        return CommandResult(stdout="operator\n", stderr="", exit_code=0)


def test_plan_step_rejects_extra_fields() -> None:
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        PlanStep.model_validate(
            {
                "step_id": "bad",
                "intent": "bad",
                "capability": "process.kill",
                "args": {},
                "truly_unknown_field": "fail",
            }
        )


def test_system_current_user_output_matches_registered_contract() -> None:
    output = SystemTools(FakeRunner()).current_user()

    assert output.data == {"username": "operator"}


def test_process_kill_uses_declared_signal_enum_and_structured_success() -> None:
    runner = FakeRunner()
    output = ProcessTools(runner).kill(pid=1234, signal="TERM", port=8080)

    assert runner.calls == [["kill", "-TERM", "1234"]]
    assert output.data == {"ok": True, "pid": 1234, "signal": "TERM", "port": 8080}


def test_legacy_ref_dict_is_rejected_by_static_validation_and_resolver() -> None:
    plan = ExecutionPlan(
        plan_id="legacy-ref-denied",
        goal="reject legacy reference",
        language="en",
        steps=[
            PlanStep(
                step_id="find",
                capability="process.find_by_port",
                args={"port": 8080},
                expected_outputs={"pids": "array"},
                justification="Find process.",
                on_failure="stop",
            ),
            PlanStep(
                step_id="kill",
                capability="process.kill",
                args={"pid": {"ref": "find.pids[0]"}, "signal": "TERM"},
                depends_on=["find"],
                expected_outputs={"ok": "boolean"},
                justification="Stop process.",
                on_failure="stop",
            ),
        ],
        verification_strategy="legacy references are unsafe",
        verification_no_meaningful_verifier=True,
    )

    result = validate_plan(plan, build_default_capability_registry())

    assert not result.valid
    assert any(error.code == "legacy_reference_forbidden" for error in result.errors)
    with pytest.raises(ValueError, match="Legacy reference syntax is forbidden"):
        resolve_args(
            plan.steps[1].args,
            plan=plan,
            authorized_outputs={"find": {"pids": [1234]}},
        )


def test_reference_resolution_requires_authorized_outputs_mapping() -> None:
    plan = ExecutionPlan(
        plan_id="missing-authorized-outputs",
        goal="resolve references",
        language="en",
        steps=[
            PlanStep(
                step_id="find",
                capability="process.find_by_port",
                args={"port": 8080},
                expected_outputs={"pids": "array"},
                justification="Find process.",
                on_failure="stop",
            )
        ],
    )

    with pytest.raises(ValueError, match="authorized_outputs is required"):
        resolve_args(plan.steps[0].args, plan=plan)


def test_registered_capability_schemas_are_closed_objects() -> None:
    registry = build_default_capability_registry()

    for capability in registry.all():
        assert capability.input_schema.get("additionalProperties") is False
        assert capability.output_schema.get("additionalProperties") is False


def test_static_validator_rejects_enum_and_range_violations() -> None:
    plan = ExecutionPlan(
        plan_id="schema-hardening",
        goal="reject invalid capability args",
        language="en",
        steps=[
            PlanStep(
                step_id="find",
                capability="process.find_by_port",
                args={"port": 70000},
                expected_outputs={"pids": "array"},
                justification="Invalid port must fail schema validation.",
                on_failure="stop",
            ),
            PlanStep(
                step_id="kill",
                capability="process.kill",
                args={"pid": 1234, "signal": "HUP"},
                expected_outputs={"ok": "boolean"},
                justification="Invalid signal must fail schema validation.",
                on_failure="stop",
            ),
        ],
        verification_strategy="invalid args do not execute",
        verification_no_meaningful_verifier=True,
    )

    result = validate_plan(plan, build_default_capability_registry())

    assert not result.valid
    codes = {error.code for error in result.errors}
    assert "arg_range_violation" in codes
    assert "arg_enum_violation" in codes


def test_policy_denies_tier0_when_target_scope_is_not_explicit() -> None:
    decision = evaluate_policy(
        capability_name="system.service_status",
        resolved_args={"service": "nginx"},
        argument_provenance={"service": "literal_or_validated_user_input"},
        environment=EnvironmentState(),
        target_scope="implicit",
    )

    assert decision.decision == PolicyDecisionValue.DENY
    assert decision.matched_rule_id == "scope.explicit_required"
    assert "deny_by_default" in decision.reason_codes


def test_policy_denies_missing_canonical_invocation_contract() -> None:
    decision = evaluate_policy(
        capability_name=None,
        resolved_args=None,
        environment=EnvironmentState(),
    )

    assert decision.decision == PolicyDecisionValue.DENY
    assert decision.matched_rule_id == "default.invalid_invocation_contract"
    assert "invalid_policy_invocation" in decision.reason_codes


def test_runtime_normalizes_and_redacts_adapter_exceptions() -> None:
    capability = build_default_capability_registry().require("system.current_user")

    outcome = ControlledAdapterRuntime(RaisingRegistry()).execute(
        capability=capability,
        normalized_args={},
    )

    assert outcome.status == "adapter_failure"
    assert outcome.normalized_output["failure_class"] == "adapter_failure"
    assert "supersecret" not in str(outcome.normalized_output)
    assert "abcdef1234567890" not in str(outcome.normalized_output)
    assert outcome.redaction_metadata["redacted"] is True


def test_runtime_rejects_output_missing_required_field() -> None:
    capability = build_default_capability_registry().require("system.current_user")

    outcome = ControlledAdapterRuntime(OutputRegistry({"system.current_user": {}})).execute(
        capability=capability,
        normalized_args={},
    )

    assert outcome.status == "output_schema_validation_failed"
    assert outcome.normalized_output["failure_class"] == "output_schema_validation_failure"
    assert "username" in str(outcome.normalized_output["validation_errors"])


def test_runtime_rejects_output_with_wrong_type_range_and_enum() -> None:
    capability = build_default_capability_registry().require("process.kill")

    outcome = ControlledAdapterRuntime(
        OutputRegistry(
            {
                "process.kill": {
                    "ok": "yes",
                    "pid": 0,
                    "signal": "HUP",
                }
            }
        )
    ).execute(
        capability=capability,
        normalized_args={"pid": 1234, "signal": "TERM"},
    )

    assert outcome.status == "output_schema_validation_failed"
    errors = " ".join(str(error) for error in outcome.normalized_output["validation_errors"])
    assert "ok" in errors
    assert "pid" in errors
    assert "signal" in errors


def test_schema_validator_supports_high_value_json_schema_features() -> None:
    schema = {
        "type": "object",
        "required": ["mode", "items", "meta"],
        "properties": {
            "mode": {"const": "safe"},
            "items": {
                "type": "array",
                "minItems": 2,
                "uniqueItems": True,
                "contains": {"type": "integer", "minimum": 10},
                "items": {"anyOf": [{"type": "integer"}, {"type": "string", "pattern": "^ok-"}]},
            },
            "meta": {
                "allOf": [
                    {
                        "type": "object",
                        "required": ["attempts"],
                        "properties": {"attempts": {"type": "integer", "multipleOf": 2}},
                        "additionalProperties": {"type": "string"},
                    },
                    {"not": {"required": ["secret"]}},
                ]
            },
            "result": {"oneOf": [{"type": "boolean"}, {"type": "null"}]},
        },
        "additionalProperties": False,
    }

    valid = validate_schema_value(
        {"mode": "safe", "items": [2, "ok-ready", 12], "meta": {"attempts": 4}, "result": None},
        schema,
    )
    invalid = validate_schema_value(
        {
            "mode": "unsafe",
            "items": [2, 2],
            "meta": {"attempts": 3, "secret": "present"},
            "result": "yes",
        },
        schema,
    )

    assert valid.valid
    assert not invalid.valid
    errors = " ".join(invalid.errors)
    assert "const" in errors
    assert "uniqueItems" in errors
    assert "multipleOf" in errors
    assert "not schema" in errors
    assert "oneOf" in errors


def test_schema_validator_fails_closed_for_unsupported_features() -> None:
    result = validate_schema_value("operator@example.com", {"type": "string", "format": "email"})

    assert not result.valid
    assert result.errors == ["$: unsupported schema keyword 'format'"]


def _test_capability(
    *,
    input_schema: dict[str, object],
    output_schema: dict[str, object] | None = None,
) -> CapabilityDefinition:
    return CapabilityDefinition(
        name="test.capability",
        version=1,
        verb="read",
        object="test",
        risk_tier=RiskTier.TIER_0,
        approval_mode=ApprovalMode.AUTO,
        allowed_environments=["dev"],
        allowed_actor_types=["assistant"],
        scope_model={},
        input_schema=input_schema,
        output_schema=output_schema or {"type": "object", "additionalProperties": False},
        runtime_constraints=RuntimeConstraints(),
        adapter_id="test.capability",
        is_read_only=True,
        preview_builder="default",
        verification_recommendation="none",
        redaction_policy="standard",
        prompt=CapabilityPrompt(
            instructions="Inspect only the validated test capability scope.",
            constraints=["Do not invent structured output."],
        ),
    )


def test_capability_registry_rejects_unsupported_schema_keywords_at_registration() -> None:
    capability = _test_capability(
        input_schema={
            "type": "object",
            "properties": {"email": {"type": "string", "format": "email"}},
            "additionalProperties": False,
        }
    )

    with pytest.raises(ValueError, match="unsupported schema keyword 'format'"):
        CapabilityRegistry([capability])


def test_capability_registry_rejects_malformed_schemas_at_registration() -> None:
    capability = _test_capability(
        input_schema={
            "type": "object",
            "properties": [],
            "additionalProperties": False,
        }
    )

    with pytest.raises(ValueError, match="properties must be an object"):
        CapabilityRegistry([capability])


def test_capability_schema_documentation_matches_validator_keywords() -> None:
    doc = Path("docs/architecture/capability-schema.md").read_text()

    for keyword in sorted(SUPPORTED_SCHEMA_KEYWORDS):
        assert f"`{keyword}`" in doc
    assert "fail closed" in doc
    assert "xfusion/capabilities/schema.py" in doc


def test_docs_make_v02_normative_and_archive_v01_materials() -> None:
    readme = Path("README.md").read_text()
    assert "docs/specs/xfusion-v0.2.md" in readme
    assert "docs/specs/xfusion-v0.1.md" not in readme

    archive_root = Path("docs/archive")
    archived_docs = sorted(archive_root.rglob("*.md"))
    assert archived_docs
    for path in archived_docs:
        doc = path.read_text()
        assert doc.startswith("> [!IMPORTANT]\n> Historical, non-normative")
        assert "docs/specs/xfusion-v0.2.md" in doc

    active_docs = [
        path
        for path in Path("docs").rglob("*.md")
        if "archive" not in path.parts and path != Path("docs/specs/xfusion-v0.2.md")
    ]
    for path in active_docs:
        doc = path.read_text()
        assert "XFusion v0.1" not in doc


def test_malformed_output_is_audited_and_never_becomes_referenceable() -> None:
    plan = ExecutionPlan(
        plan_id="malformed-output-flow",
        goal="reject malformed upstream output",
        language="en",
        steps=[
            PlanStep(
                step_id="find",
                capability="process.find_by_port",
                args={"port": 8080},
                expected_outputs={"pids": "array"},
                justification="Find process.",
                on_failure="stop",
            ),
            PlanStep(
                step_id="kill",
                capability="process.kill",
                args={"pid": "$steps.find.outputs.pids[0]", "signal": "TERM"},
                depends_on=["find"],
                expected_outputs={"ok": "boolean"},
                justification="Stop process from prior output.",
                on_failure="stop",
            ),
        ],
        verification_strategy="verify process stop",
        verification_no_meaningful_verifier=True,
    )
    registry = OutputRegistry({"process.find_by_port": {"pids": "not-a-list", "stdout": ""}})
    graph = build_agent_graph(registry).compile()

    state = graph.invoke(
        {
            "user_input": "reject malformed output",
            "environment": EnvironmentState(),
            "language": "en",
            "plan": plan,
            "current_step_id": None,
            "policy_decision": None,
            "verification_result": None,
            "last_tool_output": None,
            "step_outputs": {},
            "pending_confirmation_phrase": None,
            "response": "",
            "audit_records": [],
        }
    )

    assert registry.executed_tools == ["process.find_by_port"]
    assert state["step_outputs"] == {}
    assert state["authorized_step_outputs"] == {}
    assert state["plan"].steps[0].authorized_output_accepted is False
    assert state["plan"].steps[1].status == "pending"
    assert any(
        record["status"] == "output_schema_validation_failed" for record in state["audit_records"]
    )
    audit_record = next(
        record
        for record in state["audit_records"]
        if record["status"] == "output_schema_validation_failed"
    )
    assert audit_record["normalized_output"] == {}
    assert audit_record["action_taken"]["failure_class"] == "output_schema_validation_failure"


def _one_step_graph_state(
    plan: ExecutionPlan, user_input: str = "fault injection"
) -> dict[str, Any]:
    return {
        "user_input": user_input,
        "environment": EnvironmentState(),
        "language": "en",
        "plan": plan,
        "current_step_id": None,
        "policy_decision": None,
        "verification_result": None,
        "last_tool_output": None,
        "step_outputs": {},
        "authorized_step_outputs": {},
        "pending_confirmation_phrase": None,
        "response": "",
        "audit_records": [],
    }


def _current_user_plan(plan_id: str) -> ExecutionPlan:
    return ExecutionPlan(
        plan_id=plan_id,
        goal="inspect current user",
        language="en",
        steps=[
            PlanStep(
                step_id="whoami",
                capability="system.current_user",
                args={},
                expected_outputs={"username": "string"},
                justification="Read current user.",
                on_failure="stop",
            )
        ],
    )


def _assert_failure_is_audited_closed(
    state: dict[str, Any],
    *,
    failure_class: str,
) -> None:
    assert state["step_outputs"] == {}
    assert state["authorized_step_outputs"] == {}
    assert SECRET not in str(state["audit_records"])
    assert SECRET not in str(state["response"])
    records = [
        record
        for record in state["audit_records"]
        if isinstance(record, dict) and record.get("status") == failure_class
    ]
    assert records
    record = records[-1]
    assert record["action_taken"]["failure_class"] == failure_class
    assert record["normalized_output"] == {}
    final = state["audit_records"][-1]
    assert final["event"] == "final_explanation_snapshot"
    assert final["source_audit_status"] == failure_class
    assert final["response"] == state["response"]


def test_runtime_timeout_fails_closed_end_to_end() -> None:
    graph = build_agent_graph(TimeoutRegistry()).compile()

    state = graph.invoke(_one_step_graph_state(_current_user_plan("timeout-fault")))

    _assert_failure_is_audited_closed(state, failure_class="runtime_timeout")


def test_internal_system_failure_fails_closed_end_to_end() -> None:
    graph = build_agent_graph(BrokenReturnRegistry()).compile()

    state = graph.invoke(_one_step_graph_state(_current_user_plan("internal-fault")))

    _assert_failure_is_audited_closed(state, failure_class="internal_system_failure")


def test_redaction_failure_fails_closed_end_to_end(monkeypatch: pytest.MonkeyPatch) -> None:
    def broken_redaction(value: object) -> tuple[object, dict[str, object]]:
        raise RuntimeError(f"redactor unavailable for {SECRET}")

    monkeypatch.setattr("xfusion.execution.runtime.redact_value", broken_redaction)
    graph = build_agent_graph(
        OutputRegistry({"system.current_user": {"username": f"operator {SECRET}"}})
    ).compile()

    state = graph.invoke(_one_step_graph_state(_current_user_plan("redaction-fault")))

    _assert_failure_is_audited_closed(state, failure_class="redaction_failure")


def test_scope_violation_fails_closed_end_to_end() -> None:
    plan = ExecutionPlan(
        plan_id="scope-violation",
        goal="mutate protected path",
        language="en",
        steps=[
            PlanStep(
                step_id="cleanup",
                capability="cleanup.safe_disk_cleanup",
                args={"approved_paths": ["/etc"], "execute": True},
                expected_outputs={"ok": "boolean"},
                justification="Protected path mutation must fail closed.",
                on_failure="stop",
            )
        ],
        verification_strategy="protected path denial",
    )
    registry = OutputRegistry({"cleanup.safe_disk_cleanup": {"ok": True}})
    graph = build_agent_graph(registry).compile()

    state = graph.invoke(_one_step_graph_state(plan, user_input=f"cleanup /etc {SECRET}"))

    assert registry.executed_tools == []
    _assert_failure_is_audited_closed(state, failure_class="scope_violation")


def test_reasoning_role_contracts_reject_authority_and_wrong_proposal_types() -> None:
    forbidden = RoleProposal(
        role=ReasoningRole.PLANNING,
        proposal_type="workflow_dag",
        payload={"capability": "process.kill"},
        requested_authority=["execute", "approve"],
    )
    wrong_type = RoleProposal(
        role=ReasoningRole.OBSERVATION,
        proposal_type="workflow_dag",
        payload={"capability": "process.kill"},
    )
    allowed = RoleProposal(
        role=ReasoningRole.OBSERVATION,
        proposal_type="tier_0_capability",
        payload={"capability": "system.current_user", "risk_tier": "tier_0"},
    )

    forbidden_result = validate_role_proposal(forbidden)
    wrong_type_result = validate_role_proposal(wrong_type)
    allowed_result = validate_role_proposal(allowed)

    assert not forbidden_result.valid
    assert any("non-authoritative" in error for error in forbidden_result.errors)
    assert not wrong_type_result.valid
    assert any("not allowed" in error for error in wrong_type_result.errors)
    assert allowed_result.valid


def test_policy_denial_emits_structured_audit_record() -> None:
    plan = ExecutionPlan(
        plan_id="policy-denial-audit",
        goal="explain forbidden action",
        language="en",
        steps=[
            PlanStep(
                step_id="deny",
                capability="plan.explain_action",
                args={"path": "/etc", "action": "delete"},
                expected_outputs={"reason": "string"},
                justification="Unsafe action should be denied.",
                on_failure="stop",
            )
        ],
    )
    graph = build_agent_graph(OutputRegistry({})).compile()

    state = graph.invoke(
        {
            "user_input": "delete /etc",
            "environment": EnvironmentState(),
            "language": "en",
            "plan": plan,
            "current_step_id": None,
            "policy_decision": None,
            "verification_result": None,
            "last_tool_output": None,
            "step_outputs": {},
            "pending_confirmation_phrase": None,
            "response": "",
            "audit_records": [],
        }
    )

    audit_record = next(record for record in state["audit_records"] if record.get("status"))
    assert audit_record["status"] == "policy_denial"
    assert audit_record["action_taken"]["failure_class"] == "policy_denial"
    assert audit_record["action_taken"]["policy_decision"]["decision"] == "deny"
    assert state["audit_records"][-1]["source_audit_status"] == "policy_denial"


def test_verification_failure_emits_audit_record_from_authoritative_state() -> None:
    plan = ExecutionPlan(
        plan_id="verification-failure-audit",
        goal="verify port is free",
        language="en",
        steps=[
            PlanStep(
                step_id="verify_port",
                capability="process.find_by_port",
                args={"port": 8080, "expect_free": True},
                expected_outputs={"pids": "array"},
                justification="Check port.",
                on_failure="stop",
            )
        ],
    )
    registry = OutputRegistry({"process.find_by_port": {"pids": [1234], "stdout": ""}})
    graph = build_agent_graph(registry).compile()

    state = graph.invoke(
        {
            "user_input": "verify port free",
            "environment": EnvironmentState(),
            "language": "en",
            "plan": plan,
            "current_step_id": None,
            "policy_decision": None,
            "verification_result": None,
            "last_tool_output": None,
            "step_outputs": {},
            "pending_confirmation_phrase": None,
            "response": "",
            "audit_records": [],
        }
    )

    audit_record = next(record for record in state["audit_records"] if record.get("status"))
    assert audit_record["status"] == "verification_failure"
    assert audit_record["verification_result"]["success"] is False
    assert audit_record["normalized_output"] == {"pids": [1234], "stdout": ""}
    assert state["audit_records"][-1]["source_audit_status"] == "verification_failure"


def test_approval_invalidation_emits_audit_and_blocks_reuse() -> None:
    plan = ExecutionPlan(
        plan_id="approval-invalidation-audit",
        goal="stop process",
        language="en",
        steps=[
            PlanStep(
                step_id="kill",
                capability="process.kill",
                args={"pid": 1234, "signal": "TERM"},
                expected_outputs={"ok": "boolean"},
                justification="Stop bounded process.",
                on_failure="stop",
            )
        ],
        verification_strategy="verify process stop",
    )
    registry = OutputRegistry({"process.kill": {"ok": True, "pid": 1234, "signal": "TERM"}})
    graph = build_agent_graph(registry).compile()
    state = graph.invoke(
        {
            "user_input": "stop process",
            "environment": EnvironmentState(),
            "language": "en",
            "plan": plan,
            "current_step_id": None,
            "policy_decision": None,
            "verification_result": None,
            "last_tool_output": None,
            "step_outputs": {},
            "pending_confirmation_phrase": None,
            "response": "",
            "audit_records": [],
        }
    )
    state["user_input"] = state["pending_confirmation_phrase"]
    state = graph.invoke(state)
    registry.executed_tools.clear()

    state["plan"].steps[0].status = StepStatus.PENDING
    state["plan"].steps[0].args = {"pid": 9999, "signal": "TERM"}
    state["plan"].steps[0].args = {"pid": 9999, "signal": "TERM"}
    state["plan"].interaction_state = InteractionState.EXECUTING
    state["plan"].status = "executing"
    state = graph.invoke(state)

    assert registry.executed_tools == []
    audit_record = [
        record
        for record in state["audit_records"]
        if record.get("status") == "approval_invalidated"
    ][-1]
    assert audit_record["action_taken"]["failure_class"] == "approval_invalidated"
    assert state["audit_records"][-1]["source_audit_status"] == "approval_invalidated"
