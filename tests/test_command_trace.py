from __future__ import annotations

from typing import Any

from xfusion.domain.models.environment import EnvironmentState
from xfusion.execution.command_runner import CommandRunner
from xfusion.graph.wiring import build_agent_graph
from xfusion.tools.disk import DiskTools
from xfusion.tools.process import ProcessTools
from xfusion.tools.registry import ToolRegistry
from xfusion.tools.system import SystemTools


def _registry() -> ToolRegistry:
    runner = CommandRunner()
    return ToolRegistry(SystemTools(runner), DiskTools(runner), ProcessTools(runner))


def test_registry_records_single_command_trace_entry() -> None:
    registry = _registry()
    output = registry.execute("system.current_user", {})

    assert output.summary
    trace = registry.last_execution_trace
    assert len(trace) == 1
    entry = trace[0]
    assert entry["planned_argv"] == ["id", "-un"]
    assert entry["ran_argv"] == ["id", "-un"]
    assert isinstance(entry["exit_code"], int)
    assert isinstance(entry["duration_ms"], int)
    assert "started_at" in entry
    assert "ended_at" in entry


def test_registry_records_multi_command_trace_entries() -> None:
    registry = _registry()
    output = registry.execute("system.detect_os", {})

    assert output.summary
    trace = registry.last_execution_trace
    assert len(trace) >= 3
    first = trace[0]
    assert isinstance(first["planned_argv"], list)
    assert isinstance(first["stdout_excerpt"], str)
    assert isinstance(first["stderr_excerpt"], str)


def test_completed_read_only_response_uses_command_transcript_contract() -> None:
    registry = _registry()
    graph = build_agent_graph(registry).compile()

    state: dict[str, Any] = {
        "user_input": "check disk usage",
        "environment": EnvironmentState(distro_family="ubuntu", sudo_available=True),
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
        "response_mode": "normal",
    }
    result = graph.invoke(state)

    assert result["plan"].interaction_state == "completed"
    response = result["response"]
    assert "About to run:" in response
    assert "Ran:" in response
    assert "Output:" in response
    assert "What this means:" in response
