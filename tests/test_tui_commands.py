from __future__ import annotations

import logging
from collections import deque
from typing import Any, cast
from unittest.mock import AsyncMock, MagicMock

import pytest
from textual.app import App, ComposeResult

from xfusion.app.commands.core import ExitCommand, HelpCommand, ResetCommand
from xfusion.app.commands.info import AuditCommand, ListCommand, TemplatesCommand
from xfusion.app.commands.registry import CommandRegistry
from xfusion.app.tui import AgentMessage, StepWidget, TuiDebugLogHandler, XFusionTUI
from xfusion.app.turns import non_operational_response
from xfusion.app.widgets.modals import ApprovalModal
from xfusion.app.widgets.palette import CommandItem, CommandPalette
from xfusion.conversation.gateway import ClarificationResponse, IntentDecision
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


def _fallback_step() -> PlanStep:
    return PlanStep(
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


def test_step_widget_normal_mode_renders_compact_showcase_summary():
    rendered = StepWidget(_fallback_step(), {"summary": "Kernel details captured."}).render().plain

    assert "SUCCESS" in rendered
    assert "shell.fallback" in rendered
    assert "risk=privileged" in rendered
    assert "approval=approved" in rendered
    assert "Kernel details captured." in rendered
    assert "Surface: restricted_shell" not in rendered
    assert "Fingerprint:" not in rendered
    assert "argv: uname -a" not in rendered


def test_step_widget_debug_mode_renders_hybrid_policy_and_runtime_metadata():
    step = _fallback_step()

    rendered = StepWidget(step, {"summary": "Kernel details captured."}, debug=True).render().plain

    assert "Surface: restricted_shell" in rendered
    assert "Policy: write_safe" in rendered
    assert "Final risk: privileged" in rendered
    assert "Escalated: yes" in rendered
    assert "Fallback: No registered capability" in rendered
    assert "Approval: approved" in rendered
    assert "argv: uname -a" in rendered
    assert "stdout: Darwin host 25.0.0" in rendered


class PaletteHarness(App):
    def compose(self) -> ComposeResult:
        yield CommandPalette(id="palette")


@pytest.mark.anyio
async def test_command_palette_selection_returns_selected_command():
    help_cmd = HelpCommand()
    exit_cmd = ExitCommand()

    async with PaletteHarness().run_test() as pilot:
        palette = pilot.app.query_one("#palette", CommandPalette)
        first = CommandItem(help_cmd)
        second = CommandItem(exit_cmd)
        first.add_class("selected")
        palette.mount(first)
        palette.mount(second)
        await pilot.pause()

        assert palette.get_selected() is help_cmd


def test_approval_modal_escape_dismisses_without_phrase():
    modal = ApprovalModal("APPROVE 123")
    event = MagicMock()
    event.key = "escape"
    dismiss = MagicMock()
    cast(Any, modal).dismiss = dismiss

    modal.on_key(event)

    dismiss.assert_called_once_with(None)


def test_tui_startup_banner_is_compact_not_technical_block():
    assert "XFusion Guardian v0.2.4.4" not in XFusionTUI.startup_message("normal")
    assert "Working dir:" not in XFusionTUI.startup_message("normal")
    assert "Ready" in XFusionTUI.startup_message("normal")


def test_legacy_step_widget_import_still_available():
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

    assert "approval=approved" in rendered


def test_structured_clarification_response_is_ready_for_tui_display():
    decision = IntentDecision(
        mode="clarify",
        requires_execution=False,
        confidence=0.91,
        rationale="Deletion target is missing.",
        clarification=ClarificationResponse(
            question="Which file should I delete?",
            missing_fields=["path"],
            risk_hint="Deletion requires an exact path.",
        ),
    )

    response = non_operational_response(decision)

    assert response.mode == "clarify"
    assert response.plan is None
    assert response.audit_records == []
    assert response.execution_surface is None
    assert "# Action Required" in response.message
    assert "Which file should I delete?" in response.message
    assert "`path`" in response.message
    assert "Deletion requires an exact path." in response.message


def test_tui_debug_log_handler_captures_formatted_log_lines():
    app = MagicMock()
    handler = TuiDebugLogHandler(app)
    record = logging.LogRecord(
        name="xfusion.conversation.gateway",
        level=logging.DEBUG,
        pathname=__file__,
        lineno=1,
        msg="conversation_gateway.llm_output raw=%s",
        args=('{"mode": "conversational"}',),
        exc_info=None,
    )

    handler.emit(record)

    app.capture_debug_log.assert_called_once_with(
        '[DEBUG] xfusion.conversation.gateway: conversation_gateway.llm_output raw={"mode": '
        '"conversational"}'
    )


def test_tui_debug_capture_ignores_logs_before_state_initializes():
    app = XFusionTUI()
    app.debug_log_lines = deque()

    app.capture_debug_log("startup log")

    assert list(app.debug_log_lines) == ["startup log"]


def test_agent_message_debug_mode_renders_gateway_logs():
    state = {
        "response_mode": "debug",
        "response": "debug response",
        "debug_logs": ["[DEBUG] xfusion.conversation.gateway: conversation_gateway.llm_request"],
    }
    message = AgentMessage(state)

    rendered = message._debug_log_widgets(state)

    assert len(rendered) == 2
    header = cast(Any, rendered[0].render())
    line = cast(Any, rendered[1].render())
    assert header.plain == "Debug Logs:"
    assert "conversation_gateway.llm_request" in line.plain


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
