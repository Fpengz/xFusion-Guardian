from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError

from xfusion.capabilities.registry import build_default_capability_registry
from xfusion.domain.enums import ApprovalMode, InteractionState, PolicyDecisionValue, RiskTier
from xfusion.domain.models.capability import CapabilityDefinition, RuntimeConstraints
from xfusion.domain.models.environment import EnvironmentState
from xfusion.domain.models.execution_plan import ExecutionPlan, PlanStep
from xfusion.execution.runtime import ControlledAdapterRuntime
from xfusion.graph.wiring import build_agent_graph
from xfusion.planning.validator import validate_plan
from xfusion.policy.rules import evaluate_policy
from xfusion.security.redaction import redact_value
from xfusion.tools.base import ToolOutput


class MockRegistry:
    def __init__(self, outputs: dict[str, ToolOutput] | None = None) -> None:
        self.outputs = outputs or {}
        self.calls: list[tuple[str, dict[str, object]]] = []
        self.executed_tools: list[str] = []

    def execute(self, name: str, args: dict[str, object]) -> ToolOutput:
        self.calls.append((name, args))
        self.executed_tools.append(name)
        return self.outputs.get(name, ToolOutput(summary="ok", data={"ok": True}))


def make_graph_state(
    *,
    plan: ExecutionPlan,
    user_input: str = "test",
) -> dict[str, object]:
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
        "pending_confirmation_phrase": None,
        "response": "",
        "audit_records": [],
    }


def test_plan_step_accepts_v02_capability_args() -> None:
    step = PlanStep(
        step_id="check_disk",
        intent="Inspect disk usage.",
        capability="disk.check_usage",
        args={"path": "/"},
        expected_outputs={"percent_used": "integer"},
        justification="Inspect disk usage.",
        on_failure="Report failure.",
    )

    assert step.step_id == "check_disk"
    assert step.capability == "disk.check_usage"
    assert step.args == {"path": "/"}


def test_plan_step_rejects_unknown_extra_fields() -> None:
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        PlanStep.model_validate(
            {
                "step_id": "bad",
                "intent": "bad",
                "capability": "disk.check_usage",
                "args": {},
                "hidden_shell": "rm -rf /",
            }
        )


def test_plan_step_rejects_legacy_alias_fields_fail_closed() -> None:
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        PlanStep.model_validate(
            {
                "id": "legacy_step",
                "tool": "process.kill",
                "parameters": {"pid": 1234, "signal": "TERM"},
                "dependencies": [],
                "intent": "Legacy aliases must fail closed.",
            }
        )


def test_capability_definition_is_code_defined_and_extra_forbid() -> None:
    with pytest.raises(ValidationError):
        CapabilityDefinition(
            name="unsafe",
            version=1,
            verb="execute",
            object="shell",
            risk_tier=RiskTier.TIER_3,
            approval_mode=ApprovalMode.DENY,
            allowed_environments=["dev"],
            allowed_actor_types=["assistant"],
            scope_model={},
            input_schema={"type": "object"},
            output_schema={"type": "object"},
            runtime_constraints=RuntimeConstraints(),
            adapter_id="unsafe.shell",
            is_read_only=False,
            preview_builder="default",
            verification_recommendation="none",
            redaction_policy="standard",
            **{"command": "bash"},
        )


def test_static_validator_denies_unknown_capability_by_default() -> None:
    plan = ExecutionPlan(
        plan_id="plan-unknown",
        goal="test unknown capability",
        language="en",
        steps=[
            PlanStep(
                step_id="unknown",
                capability="shell.run",
                args={"command": "id"},
                expected_outputs={},
                justification="Should be denied.",
                on_failure="stop",
            )
        ],
    )

    result = validate_plan(plan, build_default_capability_registry())

    assert not result.valid
    assert any(error.code == "unknown_capability" for error in result.errors)


def test_static_validator_rejects_invalid_or_fabricated_reference() -> None:
    plan = ExecutionPlan(
        plan_id="plan-ref",
        goal="bad reference",
        language="en",
        steps=[
            PlanStep(
                step_id="kill",
                capability="process.kill",
                args={"pid": "$steps.locate.outputs.pid", "signal": "TERM"},
                expected_outputs={"success": "boolean"},
                justification="Reference missing locate step.",
                on_failure="stop",
            )
        ],
        verification_strategy="verify mutation result",
    )

    result = validate_plan(plan, build_default_capability_registry())

    assert not result.valid
    assert any(error.code == "unknown_reference_step" for error in result.errors)


def test_static_validator_requires_verification_strategy_for_mutation() -> None:
    plan = ExecutionPlan(
        plan_id="plan-mutation",
        goal="stop a process",
        language="en",
        steps=[
            PlanStep(
                step_id="kill",
                capability="process.kill",
                args={"pid": 1234, "signal": "TERM"},
                expected_outputs={"success": "boolean"},
                justification="Stop bounded process.",
                on_failure="stop",
            )
        ],
    )

    result = validate_plan(plan, build_default_capability_registry())

    assert not result.valid
    assert any(error.code == "missing_verification_strategy" for error in result.errors)


def test_graph_validation_blocks_unknown_capability_before_policy_or_execution() -> None:
    registry = MockRegistry()
    graph = build_agent_graph(registry).compile()
    plan = ExecutionPlan(
        plan_id="bad-capability",
        goal="bad capability",
        language="en",
        steps=[
            PlanStep(
                step_id="bad",
                capability="shell.run",
                args={"command": "id"},
                expected_outputs={},
                justification="Should fail validation.",
                on_failure="stop",
            )
        ],
    )

    result = graph.invoke(make_graph_state(plan=plan))

    assert result["plan"].interaction_state == InteractionState.FAILED
    assert result["policy_decision"] is None
    assert registry.executed_tools == []
    assert "Plan validation failed" in result["response"]
    assert result["validation_result"].errors[0].code == "unknown_capability"


def test_graph_validation_blocks_fabricated_steps_reference_before_execution() -> None:
    registry = MockRegistry()
    graph = build_agent_graph(registry).compile()
    plan = ExecutionPlan(
        plan_id="bad-ref",
        goal="bad reference",
        language="en",
        steps=[
            PlanStep(
                step_id="kill",
                capability="process.kill",
                args={"pid": "$steps.locate.outputs.pid"},
                expected_outputs={"ok": "boolean"},
                justification="Should fail validation before execution.",
                on_failure="stop",
            )
        ],
        verification_strategy="verify process stop",
    )

    result = graph.invoke(make_graph_state(plan=plan))

    assert result["plan"].interaction_state == InteractionState.FAILED
    assert registry.executed_tools == []
    assert any(
        error.code == "unknown_reference_step" for error in result["validation_result"].errors
    )


def test_graph_resolves_canonical_steps_reference_at_runtime() -> None:
    registry = MockRegistry(
        {
            "process.find_by_port": ToolOutput(summary="found", data={"pids": [1234]}),
            "process.kill": ToolOutput(summary="killed", data={"ok": True, "pid": 1234}),
        }
    )
    graph = build_agent_graph(registry).compile()
    plan = ExecutionPlan(
        plan_id="canonical-ref",
        goal="stop process on port",
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
                justification="Stop process.",
                on_failure="stop",
                verification_step_ids=["verify"],
            ),
            PlanStep(
                step_id="verify",
                capability="process.find_by_port",
                args={"port": 8080, "expect_free": True},
                depends_on=["kill"],
                expected_outputs={"pids": "array"},
                justification="Verify port is free.",
                on_failure="stop",
            ),
        ],
        verification_strategy="verify port is free after stopping process",
    )

    state = graph.invoke(make_graph_state(plan=plan))
    assert state["plan"].interaction_state == InteractionState.AWAITING_CONFIRMATION

    state["user_input"] = state["pending_confirmation_phrase"]
    state = graph.invoke(state)

    kill_call = next(call for call in registry.calls if call[0] == "process.kill")
    assert kill_call[1]["pid"] == 1234
    assert kill_call[1]["signal"] == "TERM"


def test_legacy_ref_dict_is_blocked_before_approval_or_execution() -> None:
    registry = MockRegistry(
        {
            "process.find_by_port": ToolOutput(summary="found", data={"pids": [4321]}),
            "process.kill": ToolOutput(summary="killed", data={"ok": True, "pid": 4321}),
        }
    )
    graph = build_agent_graph(registry).compile()
    plan = ExecutionPlan(
        plan_id="legacy-ref",
        goal="legacy reference",
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
                args={"pid": {"ref": "find.pids[0]"}},
                depends_on=["find"],
                expected_outputs={"ok": "boolean"},
                justification="Stop process.",
                on_failure="stop",
            ),
        ],
        verification_strategy="legacy references are rejected",
        verification_no_meaningful_verifier=True,
    )

    state = graph.invoke(make_graph_state(plan=plan))

    assert state["plan"].interaction_state == InteractionState.FAILED
    assert state["pending_confirmation_phrase"] is None
    assert registry.executed_tools == []
    assert any(
        error.code == "legacy_reference_forbidden" for error in state["validation_result"].errors
    )


def test_policy_uses_v02_allow_require_approval_deny_decisions() -> None:
    allowed = evaluate_policy(
        capability_name="system.service_status",
        resolved_args={"service": "nginx"},
        argument_provenance={"service": "literal"},
        environment=EnvironmentState(),
    )
    gated = evaluate_policy(
        capability_name="process.kill",
        resolved_args={"pid": 1234, "signal": "TERM"},
        argument_provenance={"pid": "reference:$steps.find.outputs.pids[0]"},
        environment=EnvironmentState(),
    )
    denied = evaluate_policy(
        capability_name="shell.run",
        resolved_args={"command": "id"},
        argument_provenance={"command": "model"},
        environment=EnvironmentState(),
    )

    assert allowed.decision == PolicyDecisionValue.ALLOW
    assert gated.decision == PolicyDecisionValue.REQUIRE_APPROVAL
    assert denied.decision == PolicyDecisionValue.DENY
    assert denied.matched_rule_id == "default.deny_unknown_capability"


def test_blocked_secret_read_is_denied_before_execution() -> None:
    registry = MockRegistry()
    graph = build_agent_graph(registry).compile()
    plan = ExecutionPlan(
        plan_id="secret-read",
        goal="read a secret",
        language="en",
        steps=[
            PlanStep(
                step_id="read_secret",
                capability="file.read_file",
                args={"path": "/home/app/.ssh/id_ed25519"},
                expected_outputs={"content": "string"},
                justification="Read private key.",
                on_failure="stop",
            )
        ],
    )

    result = graph.invoke(make_graph_state(plan=plan))

    assert result["plan"].interaction_state == InteractionState.REFUSED
    assert result["policy_decision"].decision == PolicyDecisionValue.DENY
    assert "secret" in result["policy_decision"].reason.lower()
    assert registry.executed_tools == []


def test_approval_record_binds_phrase_and_fingerprint() -> None:
    registry = MockRegistry(
        {"process.kill": ToolOutput(summary="killed", data={"ok": True, "pid": 1234})}
    )
    graph = build_agent_graph(registry).compile()
    plan = ExecutionPlan(
        plan_id="approval-record",
        goal="stop process",
        language="en",
        target_context={"host": "local", "port": 8080},
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
        verification_strategy="verify tool success",
    )

    state = graph.invoke(make_graph_state(plan=plan))

    approval_id = state["pending_approval_id"]
    approval = state["approval_records"][approval_id]
    assert approval.action_fingerprint
    assert approval.typed_confirmation_phrase == state["pending_confirmation_phrase"]
    assert approval.preview.normalized_args == {"pid": 1234, "signal": "TERM"}

    state["user_input"] = approval.typed_confirmation_phrase
    state = graph.invoke(state)

    assert state["approval_records"][approval_id].is_approved
    assert registry.executed_tools == ["process.kill"]


def test_stale_approval_invalidates_after_target_change() -> None:
    registry = MockRegistry()
    graph = build_agent_graph(registry).compile()
    plan = ExecutionPlan(
        plan_id="stale-approval",
        goal="stop process",
        language="en",
        target_context={"host": "local"},
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
        verification_strategy="verify tool success",
    )

    state = graph.invoke(make_graph_state(plan=plan))
    phrase = state["pending_confirmation_phrase"]
    state["user_input"] = phrase
    state = graph.invoke(state)
    registry.executed_tools.clear()

    # Rewind the approved step to simulate a repaired plan changing the target.
    state["plan"].steps[0].status = "pending"
    state["plan"].steps[0].args = {"pid": 9999, "signal": "TERM"}
    state["plan"].interaction_state = InteractionState.EXECUTING
    state["plan"].status = "executing"
    state = graph.invoke(state)

    assert "Approval invalidated" in state["response"]
    assert registry.executed_tools == []


def test_expired_approval_is_rejected() -> None:
    registry = MockRegistry()
    graph = build_agent_graph(registry).compile()
    plan = ExecutionPlan(
        plan_id="expired-approval",
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
        verification_strategy="verify tool success",
    )

    state = graph.invoke(make_graph_state(plan=plan))
    approval = state["approval_records"][state["pending_approval_id"]]
    approval.expires_at = datetime.now(UTC) - timedelta(seconds=1)
    state["user_input"] = state["pending_confirmation_phrase"]
    state = graph.invoke(state)

    assert state["plan"].interaction_state == InteractionState.ABORTED
    assert "approval_expired" in state["response"]


def test_runtime_rejects_free_form_command_arg_and_redacts_output() -> None:
    capability = build_default_capability_registry().require("system.current_user")
    rejected = ControlledAdapterRuntime(MockRegistry()).execute(
        capability=capability,
        normalized_args={"command": "id"},
    )
    assert rejected.status == "runtime_rejected"

    redacted, meta = redact_value(
        {"stdout": "password=supersecret token=abcdef1234567890 Bearer abcdef1234567890"}
    )
    assert "[REDACTED]" in redacted["stdout"]
    assert meta["redacted"] is True


def test_references_resolve_only_from_authorized_upstream_outputs() -> None:
    registry = MockRegistry(
        {
            "process.find_by_port": ToolOutput(summary="found", data={"pids": [1234]}),
            "process.kill": ToolOutput(summary="killed", data={"ok": True, "pid": 1234}),
        }
    )
    graph = build_agent_graph(registry).compile()
    plan = ExecutionPlan(
        plan_id="authorized-output",
        goal="stop process on port",
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
                justification="Stop process.",
                on_failure="stop",
            ),
        ],
        verification_strategy="verify process stopped",
        verification_no_meaningful_verifier=True,
    )
    state = make_graph_state(plan=plan)
    state["step_outputs"] = {"find": {"pids": [1234]}}

    result = graph.invoke(state)

    assert result["plan"].steps[0].authorized_output_accepted is True
    assert result["plan"].interaction_state == InteractionState.AWAITING_CONFIRMATION
