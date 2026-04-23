from __future__ import annotations

import json
from typing import Any

from xfusion.audit.jsonl_sink import JsonlAuditSink
from xfusion.audit.logger import AuditLogger
from xfusion.domain.enums import InteractionState
from xfusion.domain.models.environment import EnvironmentState
from xfusion.execution.command_runner import CommandRunner
from xfusion.graph.wiring import build_agent_graph
from xfusion.tools.disk import DiskTools
from xfusion.tools.process import ProcessTools
from xfusion.tools.registry import ToolRegistry
from xfusion.tools.system import SystemTools


def make_graph_state(user_input: str, audit_log_path: str | None = None) -> dict[str, Any]:
    runner = CommandRunner()
    system_tools = SystemTools(runner)
    registry = ToolRegistry(system_tools, DiskTools(runner), ProcessTools(runner))
    graph = build_agent_graph(registry).compile()

    state: dict[str, Any] = {
        "user_input": user_input,
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
        "audit_log_path": audit_log_path,
    }
    return graph.invoke(state)


def assert_response_contract(response: str) -> None:
    required_labels = [
        "Intent:",
        "Environment:",
        "Plan:",
        "Risk:",
        "Action:",
        "Verification:",
        "State:",
        "Next:",
    ]
    for label in required_labels:
        assert label in response


def test_success_response_contains_judge_contract_sections() -> None:
    state = make_graph_state("check disk usage")

    assert state["plan"].interaction_state == InteractionState.COMPLETED
    assert_response_contract(state["response"])
    assert "disk" in state["response"].lower()


def test_refusal_response_contains_judge_contract_sections() -> None:
    state = make_graph_state("Delete everything in /etc")

    assert state["plan"].interaction_state == InteractionState.REFUSED
    assert_response_contract(state["response"])
    assert "/etc" in state["response"]
    assert "protected" in state["response"].lower()


def test_jsonl_audit_file_receives_step_records(tmp_path) -> None:
    audit_path = tmp_path / "audit.jsonl"
    state = make_graph_state("check disk usage", audit_log_path=str(audit_path))

    assert state["plan"].interaction_state == InteractionState.COMPLETED
    lines = audit_path.read_text(encoding="utf-8").splitlines()
    assert lines

    record = json.loads(lines[-1])
    assert record["plan_id"] == state["plan"].plan_id
    assert record["step_id"] == "check_disk"
    assert record["before_state"]
    assert record["action_taken"]
    assert record["after_state"]
    assert record["verification_result"]["success"] is True
    assert record["status"] == "success"


def test_jsonl_audit_file_receives_refusal_records(tmp_path) -> None:
    audit_path = tmp_path / "audit.jsonl"
    state = make_graph_state("Delete everything in /etc", audit_log_path=str(audit_path))

    assert state["plan"].interaction_state == InteractionState.REFUSED
    lines = audit_path.read_text(encoding="utf-8").splitlines()
    assert lines

    record = json.loads(lines[-1])
    assert record["plan_id"] == state["plan"].plan_id
    assert record["step_id"] == "delete_path"
    assert record["action_taken"]["capability"] == "cleanup.safe_disk_cleanup"
    assert record["status"] == "scope_violation"
    assert record["action_taken"]["failure_class"] == "scope_violation"
    assert "protected" in record["summary"].lower()


def test_audit_logger_writes_required_schema(tmp_path) -> None:
    sink = JsonlAuditSink(str(tmp_path / "manual.jsonl"))
    logger = AuditLogger(sink)

    logger.log_step(
        plan_id="plan",
        step_id="step",
        interaction_state="completed",
        before_state={"before": True},
        action_taken={"tool": "disk.check_usage"},
        after_state={"after": True},
        verification_result={"success": True},
        step_started_at=None,
        step_ended_at=None,
        status="success",
        summary="ok",
    )

    record = json.loads((tmp_path / "manual.jsonl").read_text(encoding="utf-8"))
    assert record["before_state"] == {"before": True}
    assert record["action_taken"] == {"tool": "disk.check_usage"}
