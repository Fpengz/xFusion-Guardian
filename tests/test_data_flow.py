from __future__ import annotations

from xfusion.domain.enums import InteractionState
from xfusion.domain.models.environment import EnvironmentState
from xfusion.domain.models.execution_plan import ExecutionPlan, PlanStep
from xfusion.graph.wiring import build_agent_graph
from xfusion.tools.base import ToolOutput


class MockRegistry:
    def __init__(self, outputs=None):
        self.outputs = outputs or {}
        self.executed_tools = []
        self.calls = []  # List of (name, args)

    def execute(self, name, args):
        self.executed_tools.append(name)
        self.calls.append((name, args))

        # Mock behavior for port workflow verification
        if (
            name == "process.find_by_port"
            and len([t for t in self.executed_tools if t == "process.find_by_port"]) > 1
        ):
            return ToolOutput(summary="Port free", data={"pids": []})

        return self.outputs.get(name, ToolOutput(summary="Success", data={"ok": True}))


def test_pid_passed_step1_to_step2():
    # step 1 find_by_port -> returns pids [1234]
    mock_find = ToolOutput(summary="Found 1234", data={"pids": [1234]})
    # step 2 kill -> success
    mock_kill = ToolOutput(summary="Killed", data={"ok": True})

    registry = MockRegistry({"process.find_by_port": mock_find, "process.kill": mock_kill})

    initial_env = EnvironmentState()
    graph = build_agent_graph(registry).compile()

    state = {
        "user_input": "Stop process on port 8080",
        "environment": initial_env,
        "language": "en",
        "plan": None,
        "current_step_id": None,
        "policy_decision": None,
        "verification_result": None,
        "last_tool_output": None,
        "step_outputs": {},
        "pending_confirmation_phrase": None,
        "response": "",
        "audit_records": [],
    }

    # 1. Turn 1: executes find_by_port, reaches confirmation for kill
    state = graph.invoke(state)
    assert state["plan"].interaction_state == InteractionState.AWAITING_CONFIRMATION
    assert 1234 in state["step_outputs"]["find_process"]["pids"]

    # 2. Turn 2: confirm
    phrase = state["pending_confirmation_phrase"]
    state["user_input"] = phrase
    state = graph.invoke(state)

    # Check that kill was called with resolved pid 1234
    assert "process.kill" in registry.executed_tools
    kill_call = next(c for c in registry.calls if c[0] == "process.kill")
    assert kill_call[1]["pid"] == 1234
    assert state["plan"].interaction_state == InteractionState.COMPLETED


def test_failure_when_no_pid_found():
    # step 1 find_by_port -> returns empty pids []
    mock_find = ToolOutput(summary="None found", data={"pids": []})
    registry = MockRegistry({"process.find_by_port": mock_find})

    initial_env = EnvironmentState()
    graph = build_agent_graph(registry).compile()

    state = {
        "user_input": "Stop process on port 8080",
        "environment": initial_env,
        "language": "en",
        "plan": None,
        "current_step_id": None,
        "policy_decision": None,
        "verification_result": None,
        "last_tool_output": None,
        "step_outputs": {},
        "pending_confirmation_phrase": None,
        "response": "",
        "audit_records": [],
    }

    # Turn 1: execute find_by_port
    state = graph.invoke(state)

    # v0.2 fails closed before approval because pids[0] is not an authorized value.
    assert state["plan"].interaction_state == InteractionState.FAILED
    assert "Reference resolution failed" in state["response"]
    assert "list index out of range" in state["response"]


def test_multiple_pids_passed_safely():
    # If multiple found, currently we just take the first one pids[0]
    mock_find = ToolOutput(summary="Found multiple", data={"pids": [1234, 5678]})
    registry = MockRegistry({"process.find_by_port": mock_find})

    initial_env = EnvironmentState()
    graph = build_agent_graph(registry).compile()

    state = {
        "user_input": "Stop process on port 8080",
        "environment": initial_env,
        "language": "en",
        "plan": None,
        "current_step_id": None,
        "policy_decision": None,
        "verification_result": None,
        "last_tool_output": None,
        "step_outputs": {},
        "pending_confirmation_phrase": None,
        "response": "",
        "audit_records": [],
    }

    state = graph.invoke(state)
    state["user_input"] = state["pending_confirmation_phrase"]
    state = graph.invoke(state)

    kill_call = next(c for c in registry.calls if c[0] == "process.kill")
    assert kill_call[1]["pid"] == 1234


def test_reference_resolution_error_missing_step():
    registry = MockRegistry()
    initial_env = EnvironmentState()
    graph = build_agent_graph(registry).compile()

    # Manual plan with bad reference
    plan = ExecutionPlan(
        plan_id="bad-ref",
        goal="test",
        language="en",
        steps=[
            PlanStep(
                step_id="step1",
                intent="intent1",
                capability="system.detect_os",
                args={"target": {"ref": "nonexistent_step.data"}},
                on_failure="stop",
            )
        ],
    )

    state = {
        "user_input": "test",
        "environment": initial_env,
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

    state = graph.invoke(state)
    assert state["plan"].interaction_state == InteractionState.FAILED
    assert "Plan validation failed" in state["response"]
    assert any(
        error.code == "legacy_reference_forbidden" for error in state["validation_result"].errors
    )
