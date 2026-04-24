from __future__ import annotations

from typing import TYPE_CHECKING, cast

from xfusion.app.commands.base import BaseCommand

if TYPE_CHECKING:
    from xfusion.app.tui import XFusionTUI


class SessionsCommand(BaseCommand):
    name = "sessions"
    description = "List saved sessions."
    usage = "/sessions"
    mutates_session_state = False

    async def handle(self, app: XFusionTUI, args: list[str]) -> None:
        from rich.table import Table

        from xfusion.app.tui import Static

        sessions = app.session_manager.list_sessions()
        if not sessions:
            app.add_agent_message({"response": "✦ No saved sessions found."})
            return

        table = Table(title="Saved Sessions", box=None, show_header=True)
        table.add_column("Session ID", style="cyan")
        table.add_column("Updated At", style="magenta")
        table.add_column("Last Input", style="white")

        for s in sessions:
            table.add_row(s["id"], s["updated_at"], s["last_input"])

        app.query_one("#timeline").mount(Static(table))


class ResumeCommand(BaseCommand):
    name = "resume"
    description = "Resume a previous session."
    usage = "/resume <session_id>"
    mutates_session_state = True

    async def handle(self, app: XFusionTUI, args: list[str]) -> None:
        if not args:
            app.add_agent_message({"response": "✘ Usage: `/resume <session_id>`"})
            return

        session_id = args[0]
        try:
            state = app.session_manager.load_session(session_id)
            app.state = state
            app.session_id = session_id
            app.query_one("#timeline").remove_children()
            app.update_environment_display()
            app.add_agent_message({"response": f"✦ Resumed session **{session_id}**."})
        except FileNotFoundError:
            app.add_agent_message({"response": f"✘ Session **{session_id}** not found."})
        except Exception as e:
            app.add_agent_message({"response": f"✘ Failed to resume session: {str(e)}"})


class HistoryCommand(BaseCommand):
    name = "history"
    description = "Show recent user/agent turns in the current session."
    usage = "/history"
    mutates_session_state = False

    async def handle(self, app: XFusionTUI, args: list[str]) -> None:
        # History is already visible in the timeline, but we can provide a summary
        # or list audit records here if needed.
        # For now, let's list the audit records summary.
        records = cast(list, app.state.get("audit_records", []))
        if not records:
            app.add_agent_message({"response": "✦ No history in current session."})
            return

        history_text = "### Session History\n\n"
        for i, rec in enumerate(records[-10:]):
            rec_dict = cast(dict, rec)
            node = rec_dict.get("node", "unknown")
            msg = rec_dict.get("message", "")
            history_text += f"{i + 1}. **{node}**: {msg}\n"

        app.add_agent_message({"response": history_text})
