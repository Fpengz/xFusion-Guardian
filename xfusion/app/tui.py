from __future__ import annotations

import os
import uuid
from typing import Any, cast

from rich.markdown import Markdown
from rich.text import Text
from textual import events, work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.message import Message
from textual.screen import ModalScreen
from textual.widgets import Footer, Input, Label, RichLog, Static

from xfusion.app.commands.base import BaseCommand
from xfusion.app.commands.core import (
    ClearCommand,
    DebugCommand,
    ExitCommand,
    HelpCommand,
    ResetCommand,
)
from xfusion.app.commands.info import (
    AuditCommand,
    CompactCommand,
    ConfigCommand,
    ListCommand,
    ModelCommand,
    PermissionsCommand,
    StatusCommand,
    TemplatesCommand,
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
        status_colors = {
            StepStatus.PENDING: "#64748b",
            StepStatus.RUNNING: "#f59e0b",
            StepStatus.SUCCESS: "#10b981",
            StepStatus.FAILED: "#ef4444",
            StepStatus.SKIPPED: "#3b82f6",
            StepStatus.REFUSED: "#ef4444",
        }
        color = status_colors.get(self.step.status, "white")
        symbol = "➜" if self.step.status == StepStatus.RUNNING else "•"

        res = Text()
        if self.step.status in {StepStatus.RUNNING, StepStatus.FAILED, StepStatus.SUCCESS}:
            args_str = ", ".join(f"{k}={v}" for k, v in self.step.args.items())
            envelope = self.step.system_risk_envelope
            escalated = "yes" if envelope.get("escalated") else "no"
            policy_category = (
                self.step.policy_category.value if self.step.policy_category else "unknown"
            )
            final_risk = (
                self.step.final_risk_category.value
                if self.step.final_risk_category
                else policy_category
            )
            approval_state = (
                "approved"
                if self.step.approved_action_hash
                else ("requested" if self.step.approval_id else "not required")
            )
            fallback = (
                f"\n  [dim]Fallback: {self.step.fallback_reason}[/]"
                if self.step.fallback_reason
                else ""
            )
            fingerprint = self.step.resolution_record.get("raw_command_fingerprint")
            fingerprint_line = f"\n  [dim]Fingerprint: {fingerprint}[/]" if fingerprint else ""
            cmd_line = (
                f"\n[bold white] {symbol} Execution[/]\n"
                f"  [dim]Surface: {self.step.execution_surface.value}[/]\n"
                f"  [dim]Policy: {policy_category}[/]\n"
                f"  [dim]Final risk: {final_risk}[/]\n"
                f"  [dim]Escalated: {escalated}[/]\n"
                f"  [dim]Approval: {approval_state}[/]"
                f"{fallback}"
                f"{fingerprint_line}\n"
                f"  [dim]$ {self.step.capability} {args_str}[/]"
            )
            res.append(Text.from_markup(cmd_line))

            for entry in self.step.command_trace[-2:]:
                argv = entry.get("ran_argv") or entry.get("planned_argv")
                if isinstance(argv, list):
                    res.append("\n  argv: " + " ".join(str(part) for part in argv), style="dim")
                stdout = str(entry.get("stdout_excerpt") or "").strip()
                stderr = str(entry.get("stderr_excerpt") or "").strip()
                if stdout:
                    res.append("\n  stdout: " + stdout[:240], style="dim")
                if stderr:
                    res.append("\n  stderr: " + stderr[:240], style="dim red")

        if self.output:
            # Show summary first
            summary = self.output.get("summary", "")
            if summary:
                res.append(Text.from_markup("\n[bold white]  └ Summary[/]\n"))
                res.append(f"    {summary}", style=f"dim {color}")

            # Show raw stdout if available
            stdout = self.output.get("stdout")
            if stdout:
                res.append(Text.from_markup("\n[bold white]  └ Output[/]\n"))
                res.append(f"    {stdout.strip()}", style="dim")

        return res


class AgentMessage(Static):
    """The structured block for an agent response turn."""

    def __init__(self, state: dict[str, Any]):
        super().__init__()
        self.state = state
        self.plan_label = Label("", id="plan-info")
        self.steps_container = Vertical(id="steps")
        self.policy_label = Static("", id="policy-info")
        self.explanation_container = Vertical(
            Label("[bold cyan][Interpretation][/]", id="interpretation-header"),
            Static("", id="explanation"),
            id="explanation-block",
        )
        self.debug_container = Vertical(id="debug-info")

    def compose(self) -> ComposeResult:
        yield self.plan_label
        yield self.steps_container
        yield self.policy_label
        yield self.explanation_container
        yield self.debug_container

    def update_state(self, state: dict[str, Any]):
        self.state = state
        plan = state.get("plan")
        mode = state.get("response_mode", "normal")

        if isinstance(plan, ExecutionPlan):
            self.plan_label.update(f"[bold cyan] ➜ Plan[/]\n  • {plan.goal}")
            self.plan_label.display = True
        else:
            self.plan_label.display = False

        self.steps_container.remove_children()
        if isinstance(plan, ExecutionPlan):
            step_outputs = state.get("step_outputs", {})
            for step in plan.steps:
                output = step_outputs.get(step.step_id)
                self.steps_container.mount(StepWidget(step, output))

        explanation_label = self.explanation_container.query_one("#explanation", Static)
        header_label = self.explanation_container.query_one("#interpretation-header", Label)
        if state.get("response"):
            self.explanation_container.display = True
            symbol = "✔" if plan and plan.interaction_state == InteractionState.COMPLETED else "i"
            header_label.update(f"[bold cyan] {symbol} Summary[/]")
            explanation_label.update(Markdown(state["response"]))

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
                self.debug_container.mount(
                    Label("[bold yellow]Audit Trace:[/]", classes="debug-header")
                )
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
        background: #000000;
        padding: 1 2;
    }
    #modal-content Label {
        text-align: center;
        width: 100%;
        margin-bottom: 1;
    }
    #approval-input {
        margin-top: 1;
        border: none;
        background: #1e293b;
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
        res.append(f"/{self.command.name}", style="bold")
        if self.command.aliases:
            res.append(f" ({', '.join(f'/{a}' for a in self.command.aliases)})", style="dim")
        res.append(f" - {self.command.description}", style="italic")
        return res


class CommandPalette(VerticalScroll):
    """The floating command palette."""

    DEFAULT_CSS = """
    CommandPalette {
        display: none;
        background: #000000;
        height: auto;
        max-height: 10;
        width: 80;
        dock: bottom;
        margin-bottom: 2;
        margin-left: 2;
        padding: 0 1;
    }
    CommandPalette CommandItem {
        padding: 0 1;
        color: #94a3b8;
    }
    CommandPalette CommandItem:hover {
        background: #1e293b;
    }
    CommandPalette .selected {
        background: #10b981;
        color: #000000;
    }
    """

    def move_selection(self, direction: int) -> None:
        """Move the selection up or down."""
        items = self.query(CommandItem)
        if not items:
            return

        current_index = -1
        for i, item in enumerate(items):
            if item.has_class("selected"):
                current_index = i
                item.remove_class("selected")
                break

        new_index = (current_index + direction) % len(items)
        items[new_index].add_class("selected")
        items[new_index].scroll_visible()

    def get_selected(self) -> BaseCommand | None:
        """Return the currently selected command."""
        try:
            item = self.query_one("CommandItem.selected", CommandItem)
            return item.command
        except Exception:
            return None


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
        background: transparent;
        color: #e2e8f0;
    }
    #timeline {
        height: 1fr;
        padding: 0 2;
        overflow-y: scroll;
    }
    #sidebar {
        width: 40;
        border-left: solid #334155;
        background: transparent;
        display: none;
        padding: 1;
    }
    .user-message {
        margin: 1 0;
        color: #f8fafc;
        text-style: bold;
    }
    .shell-block {
        margin: 1 0;
        padding: 0;
    }
    AgentMessage {
        margin: 1 0;
        padding: 0;
    }
    #policy-info {
        color: #facc15;
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
        color: #10b981;
    }
    #steps {
        margin: 1 0;
        height: auto;
    }
    #explanation-block {
        margin-top: 1;
    }
    #interpretation-header {
        margin-bottom: 0;
    }
    Markdown {
        padding: 0;
    }
    Markdown H1 {
        color: #10b981;
        text-style: bold;
    }
    Markdown H2 {
        color: #3b82f6;
        text-style: bold underline;
    }
    Markdown Bullet {
        color: #facc15;
    }
    #input-container {
        dock: bottom;
        height: 3;
        padding: 0 1;
        background: #020617;
        border-top: solid #334155;
    }
    #prompt-line {
        height: 1;
        width: 100%;
        margin-top: 1;
    }
    #prompt-label {
        color: #10b981;
        text-style: bold;
        margin-right: 1;
    }
    #main-input {
        border: none;
        background: #1e293b;
        width: 1fr;
        height: 1;
        padding: 0 1;
    }
    #main-input:focus {
        border: none;
        background: #334155;
    }
    #status-bar {
        dock: top;
        height: 1;
        background: transparent;
        color: #94a3b8;
        padding: 0 1;
        text-style: bold dim;
    }
    """

    def compose(self) -> ComposeResult:
        yield Static("Initializing...", id="status-bar")
        yield VerticalScroll(id="timeline")
        yield CommandPalette(id="command-palette")
        with Horizontal(id="input-container"):
            yield Label("guardian @xfusion >", id="prompt-label")
            yield Input(
                placeholder="Type / for commands or describe an operation...",
                id="main-input",
            )
        with Vertical(id="sidebar"):
            yield Static("[bold underline]ENVIRONMENT[/]")
            yield Static("", id="side-env")
            yield Static("\n[bold underline]AUDIT LOG[/]")
            yield RichLog(id="side-audit", highlight=True, markup=True)
        yield Footer()

    def on_key(self, event: events.Key) -> None:
        """Handle global keys for palette navigation and history."""
        palette = self.query_one("#command-palette", CommandPalette)
        main_input = self.query_one("#main-input", Input)

        if palette.display:
            if event.key == "up":
                palette.move_selection(-1)
                event.prevent_default()
            elif event.key == "down":
                palette.move_selection(1)
                event.prevent_default()
            elif event.key == "tab":
                selected = palette.get_selected()
                if selected:
                    main_input.value = f"/{selected.name} "
                    main_input.focus()
                event.prevent_default()
            elif event.key == "escape":
                palette.display = False
                main_input.focus()
                event.prevent_default()
        elif main_input.has_focus:
            if event.key == "up":
                if self.input_history:
                    if self.history_index == -1:
                        self.history_index = len(self.input_history) - 1
                    elif self.history_index > 0:
                        self.history_index -= 1
                    main_input.value = self.input_history[self.history_index]
                    main_input.cursor_position = len(main_input.value)
                event.prevent_default()
            elif event.key == "down":
                if self.input_history and self.history_index != -1:
                    if self.history_index < len(self.input_history) - 1:
                        self.history_index += 1
                        main_input.value = self.input_history[self.history_index]
                    else:
                        self.history_index = -1
                        main_input.value = ""
                    main_input.cursor_position = len(main_input.value)
                event.prevent_default()

    def on_mount(self) -> None:
        self.command_registry = CommandRegistry()
        self.command_registry.register(ExitCommand())
        self.command_registry.register(HelpCommand())
        self.command_registry.register(ResetCommand())
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
        self.command_registry.register(ListCommand())
        self.command_registry.register(TemplatesCommand())
        self.command_registry.register(AuditCommand())

        self.session_manager = SessionManager()
        self.runner = CommandRunner()
        self.system_tools = SystemTools(self.runner)
        self.disk_tools = DiskTools(self.runner)
        self.process_tools = ProcessTools(self.runner)
        self.registry = ToolRegistry(self.system_tools, self.disk_tools, self.process_tools)
        self.graph = build_agent_graph(self.registry).compile()

        self.init_state()
        self.input_history: list[str] = []
        self.history_index = -1

        # Technical banner
        response_mode = str(self.state["response_mode"])
        banner = f"""[cyan]────────────────────────────────
XFusion Guardian v0.2.4.3
Connected to: local runtime
Working dir: {os.getcwd()}
Mode: {response_mode.upper()} (approval required)
Type /help for commands
────────────────────────────────[/cyan]"""
        self.query_one("#timeline").mount(Static(banner))
        self.update_prompt()

    def update_prompt(self) -> None:
        """Update the prompt label with current directory and git info."""
        cwd = os.getcwd().replace(os.path.expanduser("~"), "~")
        try:
            # Short attempt to get git branch
            res = self.runner.run(["git", "branch", "--show-current"])
            branch = res.stdout.strip() if res.exit_code == 0 else ""
            branch_str = f" ({branch})" if branch else ""
        except Exception:
            branch_str = ""

        self.query_one("#prompt-label", Label).update(f"guardian @xfusion {cwd}{branch_str} >")

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
            f"[ XFUSION GUARDIAN ]  session: {self.session_id}  |  "
            f"mode: {mode.upper()}  |  debug: {'ON' if mode == 'debug' else 'OFF'}  |  "
            f"model: {load_settings().llm_model or 'local'}"
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
            Static(f"[bold #10b981]> {text}[/]", classes="user-message")
        )

    def add_agent_message(self, state: dict[str, Any]) -> AgentMessage:
        msg = AgentMessage(state)
        self.query_one("#timeline", VerticalScroll).mount(msg)
        msg.update_state(state)
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

        # History management
        self.input_history.append(user_input)
        self.history_index = -1

        # Direct shell is intentionally unavailable in the TUI; requests must flow
        # through planning, policy, approval, and the hybrid resolver.
        if user_input.startswith("!"):
            self.add_user_message(user_input)
            self.add_agent_message(
                {
                    "response": (
                        "Direct shell execution is unavailable in the TUI. "
                        "Describe the operation in natural language so XFusion can choose "
                        "capability, template, or restricted shell with policy enforcement."
                    )
                }
            )
            return

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
