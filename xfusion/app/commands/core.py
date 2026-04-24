from __future__ import annotations

from typing import TYPE_CHECKING

from xfusion.app.commands.base import BaseCommand

if TYPE_CHECKING:
    from xfusion.app.tui import XFusionTUI


class ExitCommand(BaseCommand):
    name = "exit"
    aliases = ["quit", "q"]
    description = "Exit the TUI gracefully."
    usage = "/exit"

    async def handle(self, app: XFusionTUI, args: list[str]) -> None:
        app.exit()


class HelpCommand(BaseCommand):
    name = "help"
    aliases = ["h", "?"]
    description = "Show all available commands, aliases, and descriptions."
    usage = "/help"

    async def handle(self, app: XFusionTUI, args: list[str]) -> None:
        from rich.table import Table

        from xfusion.app.tui import Static

        table = Table(title="Available Commands", box=None, show_header=True)
        table.add_column("Command", style="cyan")
        table.add_column("Aliases", style="magenta")
        table.add_column("Description", style="white")

        # We need access to the registry. I'll assume it's attached to the app.
        for cmd in sorted(app.command_registry.get_all(), key=lambda x: x.name):
            table.add_row(
                f"/{cmd.name}",
                ", ".join(f"/{a}" for a in cmd.aliases) if cmd.aliases else "-",
                cmd.description,
            )

        app.query_one("#timeline").mount(Static(table))


class NewCommand(BaseCommand):
    name = "new"
    aliases = ["reset"]
    description = "Start a new conversation/session while keeping the TUI process alive."
    usage = "/new"

    async def handle(self, app: XFusionTUI, args: list[str]) -> None:
        # Re-initialize state
        app.init_state()
        app.query_one("#timeline").remove_children()

        app.add_agent_message({"response": "✦ New session started. How can I assist you?"})


class DebugCommand(BaseCommand):
    name = "debug"
    description = "Toggle debug mode."
    usage = "/debug"

    async def handle(self, app: XFusionTUI, args: list[str]) -> None:
        from typing import cast

        app.action_toggle_debug()
        mode = cast(str, app.state["response_mode"])
        app.add_agent_message({"response": f"✦ Debug mode is now **{mode.upper()}**."})


class ClearCommand(BaseCommand):
    name = "clear"
    aliases = ["cls"]
    description = "Clear visible terminal scrollback."
    usage = "/clear"

    async def handle(self, app: XFusionTUI, args: list[str]) -> None:
        app.query_one("#timeline").remove_children()
