from __future__ import annotations

from xfusion.domain.enums import InteractionState, StepStatus
from xfusion.domain.models.environment import EnvironmentState
from xfusion.graph.wiring import build_agent_graph
from xfusion.tools.base import ToolOutput


class MockRegistry:
    def __init__(self, outputs=None):
        self.outputs = outputs or {}
        self.executed_tools = []

    def execute(self, name, args):
        self.executed_tools.append(name)
        if name == "process.find_by_port":
            return self.outputs.get(name, ToolOutput(summary="Found", data={"pids": [1234]}))
        return self.outputs.get(name, ToolOutput(summary="Success", data={"ok": True}))


def test_3_step_port_workflow_planned():
    registry = MockRegistry()
    initial_env = EnvironmentState()
    graph = build_agent_graph(registry).compile()

    state = {
        "user_input": "Find process on port 8080 and stop it",
        "environment": initial_env,
        "language": "en",
        "plan": None,
        "current_step_id": None,
        "policy_decision": None,
        "verification_result": None,
        "last_tool_output": None,
        "pending_confirmation_phrase": None,
        "response": "",
        "audit_records": [],
    }

    # Run only up to plan node
    result = graph.invoke(state)

    plan = result["plan"]
    assert len(plan.steps) == 3
    assert plan.steps[0].capability == "process.find_by_port"
    assert plan.steps[1].capability == "process.kill"
    assert plan.steps[2].capability == "process.find_by_port"

    # Verify dependencies
    assert plan.steps[1].depends_on == ["find_process"]
    assert plan.steps[2].depends_on == ["kill_process"]


def test_strict_dependency_enforcement_on_failure():
    # Scenario: first step fails, second step should not execute
    mock_find_fail = ToolOutput(summary="No process found", data={"error": "not_found", "pids": []})
    registry = MockRegistry({"process.find_by_port": mock_find_fail})

    initial_env = EnvironmentState()
    graph = build_agent_graph(registry).compile()

    state = {
        "user_input": "Find process on port 8080 and stop it",
        "environment": initial_env,
        "language": "en",
        "plan": None,
        "current_step_id": None,
        "policy_decision": None,
        "verification_result": None,
        "last_tool_output": None,
        "pending_confirmation_phrase": None,
        "response": "",
        "audit_records": [],
    }

    result = graph.invoke(state)

    # find_process fails -> kill_process blocked -> verify_port_free blocked
    assert result["plan"].interaction_state == InteractionState.FAILED
    assert result["plan"].steps[0].status == StepStatus.FAILED
    assert result["plan"].steps[1].status == StepStatus.PENDING
    assert result["plan"].steps[2].status == StepStatus.PENDING

    # Only the first tool should have been called
    assert registry.executed_tools == ["process.find_by_port"]
    assert "one or more dependencies failed" in result["response"]


def test_executed_tools_differ_from_plan_on_refusal():
    # Scenario: policy refuses the dangerous operation
    registry = MockRegistry()
    initial_env = EnvironmentState()
    graph = build_agent_graph(registry).compile()

    state = {
        "user_input": "Delete everything in /etc",
        "environment": initial_env,
        "language": "en",
        "plan": None,
        "current_step_id": None,
        "policy_decision": None,
        "verification_result": None,
        "last_tool_output": None,
        "pending_confirmation_phrase": None,
        "response": "",
        "audit_records": [],
    }

    result = graph.invoke(state)

    # Plan should have 1 step but interaction state is REFUSED
    assert len(result["plan"].steps) == 1
    assert result["plan"].interaction_state == InteractionState.REFUSED

    # No tools should have been executed
    assert registry.executed_tools == []
    assert "cannot execute" in result["response"]


def test_executed_tools_differ_from_plan_on_abort():
    # Scenario: user aborts confirmation
    registry = MockRegistry()
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
        "pending_confirmation_phrase": None,
        "response": "",
        "audit_records": [],
    }

    # 1. First turn: reach confirmation
    state = graph.invoke(state)
    # The first step find_by_port is LOW risk, so it executes.
    # The second step kill_process is MEDIUM risk, so it waits for confirmation.
    assert state["plan"].interaction_state == InteractionState.AWAITING_CONFIRMATION
    assert registry.executed_tools == ["process.find_by_port"]

    # 2. Second turn: user sends something else (not the phrase)
    state["user_input"] = "no way"
    state = graph.invoke(state)

    assert state["plan"].interaction_state == InteractionState.ABORTED
    # kill_process should NOT have been executed
    assert "process.kill" not in registry.executed_tools
    assert len(registry.executed_tools) == 1
