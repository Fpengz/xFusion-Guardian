from typing import Any, cast
from unittest.mock import AsyncMock, MagicMock

import pytest

from xfusion.app.commands.core import ExitCommand, HelpCommand
from xfusion.app.commands.registry import CommandRegistry
from xfusion.app.tui import XFusionTUI


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
