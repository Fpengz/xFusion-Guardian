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


def test_high_risk_requires_admin_confirmation() -> None:
    decision = evaluate_policy(
        capability_name="process.kill",
        resolved_args={"pid": 1234, "signal": "TERM"},
        argument_provenance={
            "pid": "literal_or_validated_user_input",
            "signal": "literal_or_validated_user_input",
        },
        environment=EnvironmentState(),
    )

    assert decision.decision == PolicyDecisionValue.REQUIRE_CONFIRMATION
    assert decision.risk_contract is not None
    assert decision.risk_contract.risk_level == "high"
    assert decision.confirmation_type == "admin"
    assert decision.risk_contract.confirmation_type == "admin"


def test_execute_fails_closed_on_stale_policy_snapshot_hash() -> None:
    registry = RecordingRegistry()
    plan = ExecutionPlan(
        plan_id="v024-stale-snapshot",
        goal="read disk usage",
        language="en",
        steps=[
            PlanStep(
                step_id="check",
                capability="disk.check_usage",
                args={"path": "/"},
                expected_outputs={"usage": "string"},
                justification="Read disk usage.",
                on_failure="stop",
                policy_snapshot_hash="stale_snapshot_hash",
            )
        ],
    )

    state = AgentGraphState.model_validate(_state_for_plan(plan, user_input="check disk"))
    result = execute_node(state, registry=registry)

    assert result.plan is not None
    assert result.plan.steps[0].failure_class == "approval_invalidated"
    assert result.plan.steps[0].non_execution_code == "policy_integrity_mismatch"
    assert registry.calls == []


def test_changed_risk_after_approval_is_blocked_before_execution() -> None:
    registry = RecordingRegistry(
        outputs={
            "user.create": ToolOutput(summary="created", data={"exists": True}),
        }
    )
    graph = build_agent_graph(registry).compile()
    plan = ExecutionPlan(
        plan_id="v024-risk-drift",
        goal="write file",
        language="en",
        steps=[
            PlanStep(
                step_id="create_user",
                capability="user.create",
                args={"username": "demo-user"},
                expected_outputs={"exists": "boolean"},
                justification="Create bounded demo user.",
                on_failure="stop",
            )
        ],
        verification_strategy="verify policy-integrity gate",
        verification_no_meaningful_verifier=True,
    )

    state = graph.invoke(_state_for_plan(plan, user_input="create demo user"))
    assert state["plan"].interaction_state == InteractionState.AWAITING_CONFIRMATION
    phrase = state["pending_confirmation_phrase"]
    assert phrase

    # Escalate to a destructive admin-risk action after approval prompt.
    state["plan"].steps[0].capability = "user.delete"
    state["plan"].steps[0].args = {"username": "demo-user"}
    state["user_input"] = phrase
    state = graph.invoke(state)

    assert state["plan"].interaction_state == InteractionState.FAILED
    assert state["plan"].steps[0].failure_class == "approval_invalidated"
    assert state["plan"].steps[0].non_execution_code == "policy_integrity_mismatch"
    assert registry.calls == []


def test_reordered_multistep_plan_invalidates_existing_approval() -> None:
    registry = RecordingRegistry(
        outputs={
            "process.find_by_port": ToolOutput(summary="found", data={"pids": [1234]}),
            "process.kill": ToolOutput(summary="killed", data={"ok": True}),
        }
    )
    graph = build_agent_graph(registry).compile()
    plan = ExecutionPlan(
        plan_id="v024-plan-reorder",
        goal="find and kill process",
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
                justification="Kill after lookup.",
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

    state = graph.invoke(_state_for_plan(plan, user_input="kill process on 8080"))
    assert state["plan"].interaction_state == InteractionState.AWAITING_CONFIRMATION
    phrase = state["pending_confirmation_phrase"]
    assert phrase

    # Reorder pending step position after approval was requested.
    state["plan"].steps = [state["plan"].steps[1], state["plan"].steps[0]]
    state["user_input"] = phrase
    state = graph.invoke(state)

    assert state["plan"].interaction_state == InteractionState.FAILED
    assert state["plan"].steps[0].failure_class == "approval_invalidated"
    assert state["plan"].steps[0].non_execution_code == "policy_integrity_mismatch"
    assert [call[0] for call in registry.calls] == ["process.find_by_port"]


def test_audit_record_emits_normalized_machine_codes() -> None:
    registry = RecordingRegistry()
    graph = build_agent_graph(registry).compile()
    plan = ExecutionPlan(
        plan_id="v024-audit-codes",
        goal="attempt protected cleanup",
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
    record = next(r for r in state["audit_records"] if r.get("status") == "scope_violation")

    assert record["policy_decision_code"] == "deny"
    assert record["confirmation_type"] == "none"
    assert record["deny_code"] == "protected_path"
    assert record["non_execution"]["code"] in {"protected_path", "scope_violation"}


def test_cross_plan_approval_replay_fails_closed() -> None:
    registry = RecordingRegistry(
        outputs={
            "user.create": ToolOutput(summary="created", data={"exists": True}),
        }
    )
    graph = build_agent_graph(registry).compile()

    original_plan = ExecutionPlan(
        plan_id="v024-replay-origin",
        goal="create user",
        language="en",
        steps=[
            PlanStep(
                step_id="create_user",
                capability="user.create",
                args={"username": "demo-user"},
                expected_outputs={"exists": "boolean"},
                justification="Create bounded demo user.",
                on_failure="stop",
            )
        ],
        verification_strategy="verify replay guard",
        verification_no_meaningful_verifier=True,
    )
    origin_state = graph.invoke(_state_for_plan(original_plan, user_input="create demo user"))
    approval_id = origin_state["pending_approval_id"]
    assert approval_id
    approval_record = origin_state["approval_records"][approval_id]
    phrase = origin_state["pending_confirmation_phrase"]
    assert phrase

    # Attempt to replay an approval record/phrase in a different plan context.
    replay_plan = ExecutionPlan(
        plan_id="v024-replay-target",
        goal="create user",
        language="en",
        steps=[
            PlanStep(
                step_id="create_user",
                capability="user.create",
                args={"username": "demo-user"},
                expected_outputs={"exists": "boolean"},
                justification="Create bounded demo user.",
                on_failure="stop",
                approval_id=approval_id,
                confirmation_phrase=phrase,
            )
        ],
        interaction_state=InteractionState.AWAITING_CONFIRMATION,
        status="awaiting_confirmation",
        verification_strategy="verify replay guard",
        verification_no_meaningful_verifier=True,
    )
    replay_state = _state_for_plan(replay_plan, user_input=phrase)
    replay_state["approval_records"] = {approval_id: approval_record}
    replay_state["pending_approval_id"] = approval_id

    result = graph.invoke(replay_state)

    assert result["plan"].interaction_state == InteractionState.FAILED
    assert result["plan"].steps[0].failure_class == "approval_invalidated"
    assert result["plan"].steps[0].non_execution_code in {
        "material_change",
        "policy_snapshot_mismatch",
    }
    assert registry.calls == []
