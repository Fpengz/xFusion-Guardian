from __future__ import annotations

from typing import Any

from xfusion.domain.enums import InteractionState
from xfusion.domain.models.environment import EnvironmentState
from xfusion.execution.command_runner import CommandRunner
from xfusion.graph.wiring import build_agent_graph
from xfusion.tools.base import ToolOutput
from xfusion.tools.cleanup import CleanupTools


class WorkflowRegistry:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, object]]] = []
        self.cleanup_executed = False

    def execute(self, name: str, args: dict[str, Any]) -> ToolOutput:
        self.calls.append((name, args))
        if name == "disk.check_usage":
            return ToolOutput(summary="Disk usage: 94% full.", data={"usage_percent": 94})
        if name == "disk.find_large_directories":
            return ToolOutput(
                summary="Found demo cache.", data={"items": ["/tmp/xfusion-demo-big"]}
            )
        if name == "cleanup.safe_disk_cleanup":
            if args.get("execute") is True:
                self.cleanup_executed = True
                return ToolOutput(
                    summary="Deleted 1 safe cleanup candidate.",
                    data={
                        "deleted": ["/tmp/xfusion-demo-big"],
                        "reclaimed_bytes": 1024,
                        "ok": True,
                    },
                )
            return ToolOutput(
                summary="Previewed 1 safe cleanup candidate.",
                data={
                    "previewed_candidates": [{"path": "/tmp/xfusion-demo-big", "size_bytes": 1024}],
                    "reclaimed_bytes": 0,
                    "ok": True,
                },
            )
        if name == "file.preview_metadata":
            return ToolOutput(
                summary="Previewed metadata.", data={"exists": True, "path": "README.md"}
            )
        if name == "user.create":
            return ToolOutput(
                summary="Created user demoagent.", data={"username": "demoagent", "exists": True}
            )
        return ToolOutput(summary=f"Unexpected tool {name}.", data={"error": "unexpected"})


def invoke(user_input: str, registry: WorkflowRegistry) -> dict[str, Any]:
    graph = build_agent_graph(registry).compile()
    return graph.invoke(
        {
            "user_input": user_input,
            "environment": EnvironmentState(
                distro_family="ubuntu",
                sudo_available=True,
                disk_pressure="high",
                package_manager="apt",
            ),
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
    )


def test_file_metadata_preview_workflow() -> None:
    registry = WorkflowRegistry()
    state = invoke("Preview metadata for README.md", registry)

    assert state["plan"].interaction_state == InteractionState.COMPLETED
    assert [name for name, _ in registry.calls] == ["file.preview_metadata"]
    assert "Result:" in state["response"]
    assert "previewed metadata" in state["response"].lower()


def test_user_create_requires_confirmation_then_verifies() -> None:
    registry = WorkflowRegistry()
    state = invoke("Create user demoagent.", registry)

    assert state["plan"].interaction_state == InteractionState.AWAITING_CONFIRMATION
    assert registry.calls == []

    state["user_input"] = state["pending_confirmation_phrase"]
    state = build_agent_graph(registry).compile().invoke(state)

    assert state["plan"].interaction_state == InteractionState.COMPLETED
    assert [name for name, _ in registry.calls] == ["user.create"]
    assert state["verification_result"].success is True


def test_disk_pressure_wow_workflow_previews_confirms_cleans_and_verifies() -> None:
    registry = WorkflowRegistry()
    state = invoke("The disk feels full. Help me clean it safely.", registry)

    assert state["plan"].interaction_state == InteractionState.AWAITING_CONFIRMATION
    assert [name for name, _ in registry.calls] == [
        "disk.check_usage",
        "disk.find_large_directories",
        "cleanup.safe_disk_cleanup",
    ]
    assert registry.calls[-1][1]["execute"] is False
    assert registry.cleanup_executed is False

    state["user_input"] = state["pending_confirmation_phrase"]
    state = build_agent_graph(registry).compile().invoke(state)

    assert state["plan"].interaction_state == InteractionState.COMPLETED
    assert [name for name, _ in registry.calls] == [
        "disk.check_usage",
        "disk.find_large_directories",
        "cleanup.safe_disk_cleanup",
        "cleanup.safe_disk_cleanup",
        "disk.check_usage",
    ]
    assert registry.calls[3][1]["execute"] is True
    assert registry.cleanup_executed is True
    assert "Result:" in state["response"]
    assert "Verification:" in state["response"]


def test_cleanup_tool_previews_before_deleting_and_refuses_protected_path(tmp_path) -> None:
    demo_file = tmp_path / "xfusion-demo-file"
    demo_file.write_text("safe demo data", encoding="utf-8")
    tools = CleanupTools(CommandRunner())

    protected = tools.safe_disk_cleanup(approved_paths=["/etc"], execute=True)
    assert "error" in protected.data
    assert demo_file.exists()

    preview = tools.safe_disk_cleanup(approved_paths=[str(tmp_path)], execute=False)
    assert preview.data["previewed_candidates"]
    assert demo_file.exists()

    deleted = tools.safe_disk_cleanup(approved_paths=[str(tmp_path)], execute=True)
    assert deleted.data["deleted"]
    assert not demo_file.exists()
