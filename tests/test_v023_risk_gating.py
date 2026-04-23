from __future__ import annotations

from xfusion.domain.enums import InteractionState, PolicyDecisionValue
from xfusion.domain.models.environment import EnvironmentState
from xfusion.domain.models.execution_plan import ExecutionPlan, PlanStep
from xfusion.graph.nodes.execute import execute_node
from xfusion.graph.state import AgentGraphState
from xfusion.graph.wiring import build_agent_graph
from xfusion.policy.rules import evaluate_policy
from xfusion.tools.base import ToolOutput


class RecordingRegistry:
    def __init__(self, outputs: dict[str, ToolOutput] | None = None) -> None:
        self.outputs = outputs or {}
        self.calls: list[tuple[str, dict[str, object]]] = []

    def execute(self, name: str, args: dict[str, object]) -> ToolOutput:
        self.calls.append((name, args))
        return self.outputs.get(name, ToolOutput(summary="ok", data={"ok": True}))


def _state_for_plan(plan: ExecutionPlan, *, user_input: str) -> dict[str, object]:
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


def test_read_only_policy_allows_without_confirmation_and_sets_risk_contract() -> None:
    decision = evaluate_policy(
        capability_name="disk.check_usage",
        resolved_args={"path": "/"},
        argument_provenance={"path": "literal_or_validated_user_input"},
        environment=EnvironmentState(),
    )

    assert decision.decision == PolicyDecisionValue.ALLOW
    assert decision.risk_contract is not None
    assert decision.risk_contract.risk_level == "low"
    assert decision.risk_contract.requires_confirmation is False
    assert "read_only_inspection" in decision.risk_contract.side_effects


def test_mutation_policy_requires_confirmation_and_sets_step_bound_risk_contract() -> None:
    decision = evaluate_policy(
        capability_name="user.delete",
        resolved_args={"username": "demoagent"},
        argument_provenance={"username": "literal_or_validated_user_input"},
        environment=EnvironmentState(),
    )

    assert decision.decision == PolicyDecisionValue.REQUIRE_APPROVAL
    assert decision.risk_contract is not None
    assert decision.risk_contract.risk_level == "high"
    assert decision.confirmation_type == "admin"
    assert decision.risk_contract.requires_confirmation is True
    assert decision.risk_contract.confirmation_type == "admin"
    assert decision.risk_contract.privilege_required is True


def test_unknown_risky_pattern_fails_closed_with_clear_reason() -> None:
    decision = evaluate_policy(
        capability_name="cleanup.safe_disk_cleanup",
        resolved_args={
            "approved_paths": ["/tmp"],
            "candidate_class": "rm -rf /",
            "older_than_days": 7,
            "max_files": 10,
            "max_bytes": 1000,
            "execute": True,
        },
        argument_provenance={
            "approved_paths": "literal_or_validated_user_input",
            "candidate_class": "literal_or_validated_user_input",
            "older_than_days": "literal_or_validated_user_input",
            "max_files": "literal_or_validated_user_input",
            "max_bytes": "literal_or_validated_user_input",
            "execute": "literal_or_validated_user_input",
        },
        environment=EnvironmentState(),
    )

    assert decision.decision == PolicyDecisionValue.DENY
    assert decision.risk_contract is not None
    assert decision.risk_contract.risk_level == "critical"
    assert decision.risk_contract.deny_reason
    assert "unknown_risky_pattern" in decision.reason_codes


def test_dependency_workflow_respects_confirmation_gate_before_mutation_execution() -> None:
    registry = RecordingRegistry(
        outputs={
            "process.find_by_port": ToolOutput(
                summary="found",
                data={"pids": [1234], "stdout": ""},
            ),
            "process.kill": ToolOutput(
                summary="killed",
                data={"ok": True, "pid": 1234, "signal": "TERM"},
            ),
        }
    )
    graph = build_agent_graph(registry).compile()
    plan = ExecutionPlan(
        plan_id="v023-dependency-gate",
        goal="stop process on port",
        language="en",
        steps=[
            PlanStep(
                step_id="find",
                capability="process.find_by_port",
                args={"port": 8080},
                expected_outputs={"pids": "array"},
                justification="Find process first.",
                on_failure="stop",
            ),
            PlanStep(
                step_id="kill",
                capability="process.kill",
                args={"pid": "$steps.find.outputs.pids[0]", "signal": "TERM"},
                depends_on=["find"],
                expected_outputs={"ok": "boolean"},
                justification="Stop process after lookup.",
                on_failure="stop",
                verification_step_ids=["verify"],
            ),
            PlanStep(
                step_id="verify",
                capability="process.find_by_port",
                args={"port": 8080, "expect_free": True},
                depends_on=["kill"],
                expected_outputs={"pids": "array"},
                justification="Verify process is gone.",
                on_failure="stop",
            ),
        ],
        verification_strategy="verify process stop",
    )

    state = graph.invoke(_state_for_plan(plan, user_input="stop process on port 8080"))

    # Read-only dependency step executes, mutation step is gated pending confirmation.
    assert [call[0] for call in registry.calls] == ["process.find_by_port"]
    assert state["plan"].interaction_state == InteractionState.AWAITING_CONFIRMATION
    assert state["plan"].steps[1].risk_contract["requires_confirmation"] is True


def test_confirmation_cannot_be_reused_for_materially_different_args() -> None:
    registry = RecordingRegistry(
        outputs={
            "process.kill": ToolOutput(
                summary="killed",
                data={"ok": True, "pid": 1234, "signal": "TERM"},
            )
        }
    )
    graph = build_agent_graph(registry).compile()
    plan = ExecutionPlan(
        plan_id="v023-no-reuse",
        goal="stop process",
        language="en",
        steps=[
            PlanStep(
                step_id="kill",
                capability="process.kill",
                args={"pid": 1234, "signal": "TERM"},
                expected_outputs={"ok": "boolean"},
                justification="Stop process.",
                on_failure="stop",
            )
        ],
        verification_strategy="verify process stop",
    )

    state = graph.invoke(_state_for_plan(plan, user_input="stop pid 1234"))
    assert state["plan"].interaction_state == InteractionState.AWAITING_CONFIRMATION
    phrase = state["pending_confirmation_phrase"]
    assert phrase

    # Materially change invocation after approval prompt to ensure approval fingerprint mismatch.
    state["plan"].steps[0].args = {"pid": 9999, "signal": "TERM"}
    state["user_input"] = phrase
    state = graph.invoke(state)

    assert state["plan"].interaction_state == InteractionState.FAILED
    assert state["plan"].steps[0].failure_class == "approval_invalidated"
    assert state["plan"].steps[0].non_execution_code == "policy_integrity_mismatch"
    assert registry.calls == []


def test_audit_record_contains_risk_policy_confirmation_and_non_execution_fields() -> None:
    registry = RecordingRegistry()
    graph = build_agent_graph(registry).compile()
    plan = ExecutionPlan(
        plan_id="v023-audit",
        goal="delete protected path",
        language="en",
        steps=[
            PlanStep(
                step_id="cleanup",
                capability="cleanup.safe_disk_cleanup",
                args={"approved_paths": ["/etc"], "execute": True},
                expected_outputs={"ok": "boolean"},
                justification="Should be denied.",
                on_failure="stop",
            )
        ],
        verification_strategy="deny protected path mutation",
    )

    state = graph.invoke(_state_for_plan(plan, user_input="cleanup /etc"))
    assert state["plan"].interaction_state == InteractionState.REFUSED

    record = next(r for r in state["audit_records"] if r.get("status") == "scope_violation")
    assert record["original_user_request"]
    assert record["normalized_step"]["capability"] == "cleanup.safe_disk_cleanup"
    assert record["risk_classification"]["risk_level"] == "critical"
    assert record["policy_decision"]["decision"] == "deny"
    assert record["confirmation_required"] is False
    assert record["confirmation_supplied"] is False
    assert record["non_execution_reason"] == "scope_violation"


def test_execute_precheck_denial_sets_refused_plan_state_and_skips_runtime() -> None:
    registry = RecordingRegistry()
    plan = ExecutionPlan(
        plan_id="v023-execute-precheck-deny",
        goal="attempt protected cleanup",
        language="en",
        steps=[
            PlanStep(
                step_id="cleanup",
                capability="cleanup.safe_disk_cleanup",
                args={"approved_paths": ["/etc"], "execute": True},
                expected_outputs={"ok": "boolean"},
                justification="Should be denied by policy precheck.",
                on_failure="stop",
            )
        ],
        verification_strategy="deny protected path mutation",
    )
    state = AgentGraphState.model_validate(_state_for_plan(plan, user_input="cleanup /etc"))

    result = execute_node(state, registry=registry)

    assert result.plan is not None
    assert result.plan.interaction_state == InteractionState.REFUSED
    assert result.plan.status == "refused"
    assert result.plan.steps[0].status == "refused"
    assert result.plan.steps[0].failure_class == "policy_denial"
    assert registry.calls == []
