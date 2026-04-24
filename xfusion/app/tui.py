from __future__ import annotations

import uuid
from typing import Any, cast

from rich.markdown import Markdown
from rich.text import Text
from textual import work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Container, Vertical, VerticalScroll
from textual.message import Message
from textual.screen import ModalScreen
from textual.widgets import Footer, Input, Label, RichLog, Static

from xfusion.app.commands.base import BaseCommand
from xfusion.app.commands.core import (
    ClearCommand,
    DebugCommand,
    ExitCommand,
    HelpCommand,
    NewCommand,
)
from xfusion.app.commands.info import (
    CompactCommand,
    ConfigCommand,
    ModelCommand,
    PermissionsCommand,
    StatusCommand,
)
from xfusion.app.commands.registry import CommandRegistry
from xfusion.app.commands.session import HistoryCommand, ResumeCommand, SessionsCommand
from xfusion.app.sessions import SessionManager
from xfusion.app.settings import load_settings
from xfusion.domain.enums import InteractionState, StepStatus
from xfusion.domain.models.environment import EnvironmentState
from xfusion.domain.models.execution_plan import ExecutionPlan, PlanStep
from xfusion.execution.command_runner import CommandRunner
from xfusion.graph.wiring import build_agent_graph
from xfusion.tools.disk import DiskTools
from xfusion.tools.process import ProcessTools
from xfusion.tools.registry import ToolRegistry
from xfusion.tools.system import SystemTools


class AgentUpdate(Message):
    """Internal message to update the UI from the agent thread."""

    def __init__(self, state: dict[str, Any], node_name: str | None = None) -> None:
        super().__init__()
        self.state = state
        self.node_name = node_name


class StepWidget(Static):
    """Renders a single step in the execution plan."""

    def __init__(self, step: PlanStep, output: dict[str, Any] | None = None):
        super().__init__()
        self.step = step
        self.output = output

    def render(self) -> Text:
        status_icons = {
            StepStatus.PENDING: "○",
            StepStatus.RUNNING: "●",
            StepStatus.SUCCESS: "✔",
            StepStatus.FAILED: "✘",
            StepStatus.SKIPPED: "»",
            StepStatus.REFUSED: "!",
        }
        icon = status_icons.get(self.step.status, "?")

        status_colors = {
            StepStatus.PENDING: "gray",
            StepStatus.RUNNING: "yellow",
            StepStatus.SUCCESS: "green",
            StepStatus.FAILED: "red",
            StepStatus.SKIPPED: "blue",
            StepStatus.REFUSED: "red",
        }
        color = status_colors.get(self.step.status, "white")

        res = Text()
        res.append(f"  {icon} ", style=f"bold {color}")
        res.append(f"{self.step.intent or self.step.capability}", style="bold white")

        if self.step.status == StepStatus.RUNNING or self.step.status == StepStatus.FAILED:
            args_str = ", ".join(f"{k}={v}" for k, v in self.step.args.items())
            res.append(f"\n    $ {self.step.capability} {args_str}", style="dim")

        if self.output:
            summary = self.output.get("summary", "")
            if summary:
                res.append(f"\n    └ {summary}", style="dim green")

        return res


class AgentMessage(Static):
    """The structured block for an agent response turn."""

    def __init__(self, state: dict[str, Any]):
        super().__init__()
        self.state = state
        self.header = Label("[bold #a78bfa]✦ Guardian[/]", id="agent-header")
        self.thinking_label = Label("[italic #6b7280]Thinking...[/]", id="thinking")
        self.steps_container = Vertical(id="steps")
        self.policy_label = Static("", id="policy-info")
        self.explanation_label = Static("", id="explanation")
        self.debug_container = Vertical(id="debug-info")

    def compose(self) -> ComposeResult:
        yield self.header
        yield self.thinking_label
        yield self.steps_container
        yield self.policy_label
        yield self.explanation_label
        yield self.debug_container

    def update_state(self, state: dict[str, Any]):
        self.state = state
        plan = state.get("plan")
        mode = state.get("response_mode", "normal")

        if state.get("response"):
            self.thinking_label.display = False
        else:
            self.thinking_label.display = True
            if plan:
                self.thinking_label.update(f"[italic #6b7280]{plan.goal}...[/]")

        self.steps_container.remove_children()
        if isinstance(plan, ExecutionPlan):
            step_outputs = state.get("step_outputs", {})
            for step in plan.steps:
                output = step_outputs.get(step.step_id)
                self.steps_container.mount(StepWidget(step, output))

        if state.get("response"):
            self.explanation_label.update(Markdown(state["response"]))

        # Debug/Policy Info
        decision = state.get("policy_decision")
        if decision and mode == "debug":
            self.policy_label.update(f"[dim]Policy:[/] [bold]{decision}[/]")
            self.policy_label.display = True
        else:
            self.policy_label.display = False

        self.debug_container.remove_children()
        if mode == "debug":
            audit_records = state.get("audit_records", [])
            if audit_records:
                self.debug_container.mount(Label("[bold yellow]Audit Trace:[/]", id="debug-header"))
                for rec in audit_records[-5:]:  # Show last 5
                    msg = rec.get("message", str(rec))
                    self.debug_container.mount(Static(f"[dim]• {msg}[/]", classes="debug-entry"))


class ApprovalModal(ModalScreen[str]):
    """Modal screen for capturing explicit approval phrases."""

    DEFAULT_CSS = """
    ApprovalModal {
        align: center middle;
    }
    #modal-content {
        width: 60;
        height: auto;
        border: thick #ef4444;
        background: #0c0c0c;
        padding: 1 2;
    }
    #modal-content Label {
        text-align: center;
        width: 100%;
        margin-bottom: 1;
    }
    #approval-input {
        margin-top: 1;
        border: solid #ef4444;
    }
    """

    def __init__(self, phrase: str):
        super().__init__()
        self.phrase = phrase

    def compose(self) -> ComposeResult:
        with Vertical(id="modal-content"):
            yield Label("[bold #facc15]ACTION REQUIRED[/]")
            yield Label("This operation requires explicit approval.")
            yield Label("Type the following phrase exactly:")
            yield Label(f"[bold white on #b91c1c] {self.phrase} [/]")
            yield Input(placeholder="Type phrase here...", id="approval-input")
            yield Label("[italic dim]Press ESC to cancel[/]")

    def on_input_submitted(self, event: Input.Submitted) -> None:
        self.dismiss(event.value)

    def on_key(self, event) -> None:
        if event.key == "escape":
            self.dismiss(None)


class CommandItem(Static):
    """A single command entry in the palette."""

    def __init__(self, command: BaseCommand):
        super().__init__()
        self.command = command

    def render(self) -> Text:
        res = Text()
        res.append(f"/{self.command.name}", style="bold cyan")
        if self.command.aliases:
            res.append(
                f" ({', '.join(f'/{a}' for a in self.command.aliases)})", style="dim magenta"
            )
        res.append(f" - {self.command.description}", style="italic white")
        return res


class CommandPalette(VerticalScroll):
    """The floating command palette."""

    DEFAULT_CSS = """
    CommandPalette {
        display: none;
        background: #0f172a;
        border: solid #1e293b;
        height: auto;
        max-height: 10;
        width: 80;
        dock: bottom;
        margin-bottom: 3;
        margin-left: 1;
        padding: 0 1;
    }
    CommandPalette CommandItem {
        padding: 0 1;
    }
    CommandPalette CommandItem:hover {
        background: #1e293b;
    }
    CommandPalette .selected {
        background: #3b82f6;
        color: white;
    }
    """


class XFusionTUI(App):
    """The redesigned Timeline-first TUI for XFusion."""

    TITLE = "XFusion Guardian"
    BINDINGS = [
        Binding("ctrl+b", "toggle_sidebar", "Toggle Context"),
        Binding("ctrl+d", "toggle_debug", "Debug Mode"),
        Binding("ctrl+l", "clear_screen", "Clear Screen"),
        Binding("ctrl+c", "quit", "Quit"),
    ]

    CSS = """
    Screen {
        background: #0c0c0c;
        color: #e5e7eb;
    }
    #main-view {
        width: 1fr;
        height: 1fr;
    }
    #timeline {
        height: 1fr;
        padding: 1 2;
        overflow-y: scroll;
    }
    #sidebar {
        width: 40;
        border-left: solid #1e293b;
        background: #0f172a;
        display: none;
        padding: 1;
    }
    .user-message {
        margin: 1 0;
        color: #f8fafc;
        text-style: bold;
    }
    AgentMessage {
        margin: 1 0;
    }
    #policy-info {
        color: #facc15;
        margin-top: 1;
    }
    #debug-info {
        margin-top: 1;
        border: solid #334155;
        padding: 0 1;
    }
    .debug-entry {
        text-style: dim;
    }
    #agent-header {
        margin-bottom: 0;
    }
    #steps {
        margin: 1 0;
        height: auto;
    }
    #explanation {
        margin-top: 1;
    }
    #input-container {
        dock: bottom;
        height: 3;
        padding: 0 1;
        border-top: solid #1e293b;
    }
    #main-input {
        border: none;
        background: transparent;
    }
    #main-input:focus {
        border: none;
    }
    #status-bar {
        dock: top;
        height: 1;
        background: #1e293b;
        color: #94a3b8;
        padding: 0 1;
        text-style: italic;
    }
    """

    def compose(self) -> ComposeResult:
        yield Static("Initializing...", id="status-bar")
        with Container(id="main-view"):
            yield VerticalScroll(id="timeline")
            yield CommandPalette(id="command-palette")
            with Container(id="input-container"):
                yield Input(
                    placeholder="Ask XFusion Guardian (type / for commands)...", id="main-input"
                )
        with Vertical(id="sidebar"):
            yield Static("[bold underline]ENVIRONMENT[/]")
            yield Static("", id="side-env")
            yield Static("\n[bold underline]AUDIT LOG[/]")
            yield RichLog(id="side-audit", highlight=True, markup=True)
        yield Footer()

    def on_mount(self) -> None:
        self.command_registry = CommandRegistry()
        self.command_registry.register(ExitCommand())
        self.command_registry.register(HelpCommand())
        self.command_registry.register(NewCommand())
        self.command_registry.register(DebugCommand())
        self.command_registry.register(ClearCommand())
        self.command_registry.register(SessionsCommand())
        self.command_registry.register(ResumeCommand())
        self.command_registry.register(HistoryCommand())
        self.command_registry.register(StatusCommand())
        self.command_registry.register(PermissionsCommand())
        self.command_registry.register(ConfigCommand())
        self.command_registry.register(ModelCommand())
        self.command_registry.register(CompactCommand())

        self.session_manager = SessionManager()
        self.runner = CommandRunner()
        self.system_tools = SystemTools(self.runner)
        self.disk_tools = DiskTools(self.runner)
        self.process_tools = ProcessTools(self.runner)
        self.registry = ToolRegistry(self.system_tools, self.disk_tools, self.process_tools)
        self.graph = build_agent_graph(self.registry).compile()

        self.init_state()

        # Initial greeting
        self.add_agent_message(
            {
                "response": (
                    "✦ Hello! I am XFusion Guardian. "
                    "How can I assist you with your Linux environment today?"
                )
            }
        )

    def init_state(self) -> None:
        """Initialize or reset the agent state."""
        self.session_id = str(uuid.uuid4())[:8]
        settings = load_settings()
        env_output = self.system_tools.detect_os()
        initial_env = EnvironmentState.model_validate(env_output.data)

        self.state = {
            "user_input": "",
            "environment": initial_env,
            "language": "en",
            "plan": None,
            "current_step_id": None,
            "policy_decision": None,
            "verification_result": None,
            "last_tool_output": None,
            "step_outputs": {},
            "authorized_step_outputs": {},
            "pending_confirmation_phrase": None,
            "response_mode": settings.response_mode,
            "response": "",
            "audit_records": [],
            "audit_log_path": settings.audit_log_path,
        }
        self.update_environment_display()

    def update_environment_display(self) -> None:
        env = cast(EnvironmentState, self.state["environment"])
        mode = cast(str, self.state["response_mode"])
        text = (
            f"ID: {self.session_id} | {env.distro_family} {env.distro_version} | "
            f"User: {env.current_user} | Mode: {mode.upper()}"
        )
        self.query_one("#status-bar", Static).update(text)

        side_text = (
            f"Family: {env.distro_family}\n"
            f"Version: {env.distro_version}\n"
            f"User: {env.current_user}\n"
            f"Locality: {env.session_locality}"
        )
        self.query_one("#side-env", Static).update(side_text)

    def add_user_message(self, text: str) -> None:
        self.query_one("#timeline", VerticalScroll).mount(
            Static(f"[bold cyan]> {text}[/]", classes="user-message")
        )

    def add_agent_message(self, state: dict[str, Any]) -> AgentMessage:
        msg = AgentMessage(state)
        self.query_one("#timeline", VerticalScroll).mount(msg)
        msg.scroll_visible()
        return msg

    def action_clear_screen(self) -> None:
        self.query_one("#timeline").remove_children()

    def action_toggle_sidebar(self) -> None:
        sidebar = self.query_one("#sidebar")
        sidebar.display = not sidebar.display

    def action_toggle_debug(self) -> None:
        mode = "debug" if self.state["response_mode"] == "normal" else "normal"
        self.state["response_mode"] = mode
        self.update_environment_display()

    def on_input_changed(self, event: Input.Changed) -> None:
        """Show/hide command palette and filter results."""
        palette = self.query_one("#command-palette", CommandPalette)
        value = event.value.strip()

        if value.startswith("/"):
            query = value[1:].strip()
            commands = self.command_registry.search(query)
            if commands:
                palette.display = True
                palette.remove_children()
                for i, cmd in enumerate(commands):
                    item = CommandItem(cmd)
                    if i == 0:
                        item.add_class("selected")
                    palette.mount(item)
                palette.scroll_to(y=0)
            else:
                palette.display = False
        else:
            palette.display = False

    async def on_input_submitted(self, event: Input.Submitted) -> None:
        user_input = event.value.strip()
        if not user_input:
            return

        event.input.value = ""
        palette = self.query_one("#command-palette", CommandPalette)
        palette.display = False

        # Intercept slash commands
        if user_input.startswith("/"):
            parts = user_input[1:].split()
            if not parts:
                return

            trigger = parts[0]
            args = parts[1:]

            command = self.command_registry.find(trigger)
            if command:
                self.add_user_message(user_input)
                await command.handle(self, args)
                return
            else:
                self.add_agent_message(
                    {
                        "response": (
                            f"✘ Unknown command: `/{trigger}`. Type `/help` for available commands."
                        )
                    }
                )
                return

        self.add_user_message(user_input)

        # Reset transient state
        plan = self.state.get("plan")
        term_states = {
            InteractionState.COMPLETED,
            InteractionState.FAILED,
            InteractionState.REFUSED,
            InteractionState.ABORTED,
        }
        if isinstance(plan, ExecutionPlan) and plan.interaction_state in term_states:
            self.state.update(
                {
                    "plan": None,
                    "current_step_id": None,
                    "policy_decision": None,
                    "verification_result": None,
                    "last_tool_output": None,
                    "step_outputs": {},
                    "authorized_step_outputs": {},
                    "pending_confirmation_phrase": None,
                    "response": "",
                }
            )

        self.state["user_input"] = user_input
        self.active_agent_block = self.add_agent_message(self.state)
        self.run_agent()

    @work(thread=True)
    def run_agent(self) -> None:
        for update in self.graph.stream(self.state, stream_mode="updates"):
            node_name = next(iter(update.keys()))
            self.state.update(update[node_name])
            self.post_message(AgentUpdate(self.state, node_name))

    def on_agent_update(self, message: AgentUpdate) -> None:
        self.active_agent_block.update_state(message.state)
        self.active_agent_block.scroll_visible()

        if message.node_name:
            audit_log = self.query_one("#side-audit", RichLog)
            audit_log.write(f"[dim]Node:[/] [bold blue]{message.node_name}[/]")

        plan = message.state.get("plan")
        if isinstance(plan, ExecutionPlan):
            # Save session if terminal or awaiting
            term_states = {
                InteractionState.COMPLETED,
                InteractionState.FAILED,
                InteractionState.REFUSED,
                InteractionState.ABORTED,
                InteractionState.AWAITING_CONFIRMATION,
            }
            if plan.interaction_state in term_states:
                self.session_manager.save_session(self.session_id, self.state)

            if plan.interaction_state == InteractionState.AWAITING_CONFIRMATION:
                phrase = message.state.get("pending_confirmation_phrase")
                if phrase:
                    self.push_screen(ApprovalModal(phrase), callback=self.on_approval_submitted)

    def on_approval_submitted(self, phrase: str | None) -> None:
        if phrase is None:
            return

        self.add_user_message(phrase)
        self.state["user_input"] = phrase
        self.run_agent()
