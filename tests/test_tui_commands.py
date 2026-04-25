from typing import Any, cast
from unittest.mock import AsyncMock, MagicMock

import pytest

from xfusion.app.commands.core import ExitCommand, HelpCommand, ResetCommand
from xfusion.app.commands.info import AuditCommand, ListCommand, TemplatesCommand
from xfusion.app.commands.registry import CommandRegistry
from xfusion.app.tui import StepWidget, XFusionTUI
from xfusion.domain.enums import ExecutionSurface, PolicyCategory, StepStatus
from xfusion.domain.models.execution_plan import PlanStep


def test_command_registry():
    registry = CommandRegistry()
    help_cmd = HelpCommand()
    registry.register(help_cmd)

    assert registry.find("help") == help_cmd
    assert registry.find("/help") == help_cmd
    assert registry.find("h") == help_cmd
    assert registry.find("unknown") is None


def test_command_search():
    registry = CommandRegistry()
    help_cmd = HelpCommand()
    exit_cmd = ExitCommand()
    registry.register(help_cmd)
    registry.register(exit_cmd)

    results = registry.search("help")
    assert help_cmd in results
    assert exit_cmd not in results

    results = registry.search("quit")
    assert exit_cmd in results
    assert help_cmd not in results


def test_expected_tui_slash_commands_are_registered_with_supported_meanings():
    registry = CommandRegistry()
    registry.register(HelpCommand())
    registry.register(ResetCommand())
    registry.register(ListCommand())
    registry.register(TemplatesCommand())
    registry.register(AuditCommand())

    assert registry.find("/help") is not None
    assert registry.find("/new") is registry.find("/reset")
    assert registry.find("/capabilities") is registry.find("/list")
    assert registry.find("/templates") is not None
    assert registry.find("/audit") is not None


def test_step_widget_renders_hybrid_policy_and_runtime_metadata():
    step = PlanStep(
        step_id="fallback",
        capability="shell.fallback",
        args={"command": "uname -a"},
        status=StepStatus.SUCCESS,
        execution_surface=ExecutionSurface.RESTRICTED_SHELL,
        policy_category=PolicyCategory.WRITE_SAFE,
        final_risk_category=PolicyCategory.PRIVILEGED,
        system_risk_envelope={"escalated": True, "reason_codes": ["network_or_global_impact"]},
        fallback_reason="No registered capability or template covers kernel release inspection.",
        approval_id="apr_123",
        approved_action_hash="hash",
        action_fingerprint="fingerprint",
        resolution_record={"raw_command_fingerprint": "uname -a"},
        command_trace=[
            {
                "ran_argv": ["uname", "-a"],
                "stdout_excerpt": "Darwin host 25.0.0",
                "stderr_excerpt": "",
            }
        ],
    )

    rendered = StepWidget(step, {"summary": "Kernel details captured."}).render().plain

    assert "Surface: restricted_shell" in rendered
    assert "Policy: write_safe" in rendered
    assert "Final risk: privileged" in rendered
    assert "Escalated: yes" in rendered
    assert "Fallback: No registered capability" in rendered
    assert "Approval: approved" in rendered
    assert "argv: uname -a" in rendered
    assert "stdout: Darwin host 25.0.0" in rendered


@pytest.mark.anyio
async def test_slash_command_interception():
    # Mock the App
    app = MagicMock(spec=XFusionTUI)
    app.command_registry = CommandRegistry()
    exit_cmd = ExitCommand()

    # Use cast to avoid type errors during mocking
    mock_handle = AsyncMock()
    exit_cmd.handle = cast(Any, mock_handle)
    app.command_registry.register(exit_cmd)

    # Simulate on_input_submitted logic
    user_input = "/exit"
    trigger = user_input[1:]
    command = cast(Any, app.command_registry.find(trigger))

    assert command == exit_cmd
    await command.handle(app, [])
    mock_handle.assert_called_once_with(app, [])
