from __future__ import annotations

import logging
import os
import uuid
from collections import deque
from collections.abc import Iterable
from typing import Any, cast

from rich.markup import escape
from textual import events, work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import VerticalScroll
from textual.message import Message
from textual.widgets import Input, Label, RichLog, Static

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
from xfusion.app.layout import compose_main_layout
from xfusion.app.sessions import SessionManager
from xfusion.app.settings import load_settings
from xfusion.app.theme import APP_CSS
from xfusion.app.turns import enforce_routing_safety, non_operational_response
from xfusion.app.widgets import AgentMessage, ApprovalModal, CommandItem, CommandPalette, StepWidget
from xfusion.app.widgets.messages import UserMessage
from xfusion.conversation.gateway import ConversationGateway
from xfusion.domain.enums import InteractionState
from xfusion.domain.models.environment import EnvironmentState
from xfusion.domain.models.execution_plan import ExecutionPlan
from xfusion.execution.command_runner import CommandRunner
from xfusion.graph.wiring import build_agent_graph
from xfusion.tools.disk import DiskTools
from xfusion.tools.process import ProcessTools
from xfusion.tools.registry import ToolRegistry
from xfusion.tools.system import SystemTools

logger = logging.getLogger(__name__)

NEGATIVE_GATEWAY_REPLIES = {
    "n",
    "no",
    "nope",
    "cancel",
    "stop",
    "abort",
    "never mind",
    "nevermind",
}

__all__ = [
    "AgentMessage",
    "ApprovalModal",
    "CommandItem",
    "CommandPalette",
    "StepWidget",
    "TuiDebugLogHandler",
    "XFusionTUI",
]

DEBUG_LOGGER_NAMES = (
    "xfusion.conversation.gateway",
    "xfusion.app.turns",
    "xfusion.llm.client",
    "xfusion.app.tui",
)


class TuiDebugLogHandler(logging.Handler):
    """Capture XFusion debug logs so the TUI can display them in debug mode."""

    def __init__(self, app: XFusionTUI) -> None:
        super().__init__(level=logging.DEBUG)
        self.app = app
        self.setFormatter(logging.Formatter("[%(levelname)s] %(name)s: %(message)s"))

    def emit(self, record: logging.LogRecord) -> None:
        try:
            self.app.capture_debug_log(self.format(record))
        except Exception:
            self.handleError(record)


class AgentUpdate(Message):
    """Internal message to update the UI from the agent thread."""

    def __init__(self, state: dict[str, Any], node_name: str | None = None) -> None:
        super().__init__()
        self.state = state
        self.node_name = node_name


class XFusionTUI(App):
    """The redesigned Timeline-first TUI for XFusion."""

    TITLE = "XFusion Guardian"
    BINDINGS = [
        Binding("ctrl+b", "toggle_sidebar", "Toggle Context"),
        Binding("ctrl+d", "toggle_debug", "Debug Mode"),
        Binding("ctrl+l", "clear_screen", "Clear Screen"),
        Binding("ctrl+c", "quit", "Quit"),
    ]

    CSS = APP_CSS

    def compose(self) -> ComposeResult:
        yield from compose_main_layout()

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
        self.gateway = ConversationGateway.from_settings(load_settings())
        self.debug_log_lines: deque[str] = deque(maxlen=200)
        self.debug_log_handler = TuiDebugLogHandler(self)
        self.install_debug_log_handler()
        logger.info("tui.initialized session_pending=true gateway_ready=true")

        self.init_state()
        self.input_history: list[str] = []
        self.history_index = -1

        response_mode = str(self.state["response_mode"])
        self.query_one("#timeline").mount(
            Static(self.startup_message(response_mode), classes="welcome-line")
        )
        self.update_prompt()

    @staticmethod
    def startup_message(response_mode: str) -> str:
        return f"Ready · local runtime · {response_mode.upper()} mode · /help opens commands"

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
            "debug_logs": self.recent_debug_logs(),
            "audit_log_path": settings.audit_log_path,
            "pending_gateway_context": None,
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
        self.query_one("#timeline", VerticalScroll).mount(UserMessage(text))

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
        self.state["debug_logs"] = self.recent_debug_logs()
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
        logger.debug("tui.input_submitted input_length=%d", len(user_input))

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

        override_response = self._pending_gateway_reply_override(user_input)
        if override_response is not None:
            self.state["pending_gateway_context"] = None
            self.add_agent_message(
                {
                    "response": override_response,
                    "response_mode": self.state.get("response_mode", "normal"),
                    "gateway_mode": "conversational",
                    "plan": None,
                    "policy_decision": None,
                    "audit_records": [],
                    "debug_logs": self.recent_debug_logs(),
                }
            )
            return

        effective_user_input, used_pending_gateway_context = self._build_gateway_input(user_input)

        decision = enforce_routing_safety(
            self.gateway.classify(
                effective_user_input, language=str(self.state.get("language", "en"))
            )
        )
        logger.debug(
            "tui.gateway_decision mode=%s requires_execution=%s confidence=%.3f",
            decision.mode,
            decision.requires_execution,
            decision.confidence,
        )
        if decision.mode != "operational" or not decision.requires_execution:
            gateway_response = non_operational_response(decision)
            if gateway_response.mode == "clarify" and gateway_response.clarification is not None:
                self.state["pending_gateway_context"] = {
                    "context_input": effective_user_input,
                    "question": gateway_response.clarification.question,
                }
            else:
                self.state["pending_gateway_context"] = None
            logger.info(
                "tui.render_non_operational_response mode=%s requires_execution=false",
                gateway_response.mode,
            )
            self.add_agent_message(
                {
                    "response": gateway_response.message,
                    "response_mode": self.state.get("response_mode", "normal"),
                    "gateway_mode": gateway_response.mode,
                    "gateway_decision": decision,
                    "clarification": gateway_response.clarification,
                    "plan": None,
                    "policy_decision": None,
                    "audit_records": [],
                    "debug_logs": self.recent_debug_logs(),
                }
            )
            return

        self.state["pending_gateway_context"] = None
        self.state["user_input"] = effective_user_input
        self.state["debug_logs"] = self.recent_debug_logs()
        self.active_agent_block = self.add_agent_message(self.state)
        logger.info(
            "tui.run_agent_start mode=operational requires_execution=true pending_context=%s",
            "used" if used_pending_gateway_context else "unused",
        )
        self.run_agent()

    @work(thread=True)
    def run_agent(self) -> None:
        for update in self.graph.stream(self.state, stream_mode="updates"):
            node_name = next(iter(update.keys()))
            logger.debug("tui.graph_update node=%s", node_name)
            self.state.update(update[node_name])
            self.state["debug_logs"] = self.recent_debug_logs()
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

            if (
                plan.interaction_state == InteractionState.AWAITING_CONFIRMATION
                and message.node_name == "policy"
            ):
                phrase = message.state.get("pending_confirmation_phrase")
                if phrase:
                    self.push_screen(ApprovalModal(phrase), callback=self.on_approval_submitted)

    def on_approval_submitted(self, phrase: str | None) -> None:
        if phrase is None:
            return

        self.add_user_message(phrase)
        self.state["user_input"] = phrase
        self.run_agent()

    def install_debug_log_handler(self) -> None:
        for name in DEBUG_LOGGER_NAMES:
            target_logger = logging.getLogger(name)
            if self.debug_log_handler not in target_logger.handlers:
                target_logger.addHandler(self.debug_log_handler)
            target_logger.setLevel(logging.DEBUG)

    def uninstall_debug_log_handler(self) -> None:
        for name in DEBUG_LOGGER_NAMES:
            target_logger = logging.getLogger(name)
            if self.debug_log_handler in target_logger.handlers:
                target_logger.removeHandler(self.debug_log_handler)

    def on_unmount(self) -> None:
        self.uninstall_debug_log_handler()

    def capture_debug_log(self, line: str) -> None:
        if not hasattr(self, "debug_log_lines"):
            return
        self.debug_log_lines.append(line)
        if not hasattr(self, "state"):
            return
        if self.state.get("response_mode") != "debug":
            return
        self.state["debug_logs"] = self.recent_debug_logs()
        try:
            self.query_one("#side-audit", RichLog).write(f"[dim]Log:[/] {escape(line)}")
        except Exception:
            return

    def recent_debug_logs(self) -> list[str]:
        lines: Iterable[str] = getattr(self, "debug_log_lines", [])
        return list(lines)[-12:]

    def _build_gateway_input(self, user_input: str) -> tuple[str, bool]:
        pending = self.state.get("pending_gateway_context")
        if not isinstance(pending, dict):
            return user_input, False
        context_input = str(pending.get("context_input", "")).strip()
        question = str(pending.get("question", "")).strip()
        if not context_input or not question:
            return user_input, False
        return (
            "Previous user request: "
            f"{context_input}\n"
            "Clarification asked: "
            f"{question}\n"
            "User follow-up: "
            f"{user_input}",
            True,
        )

    def _pending_gateway_reply_override(self, user_input: str) -> str | None:
        pending = self.state.get("pending_gateway_context")
        if not isinstance(pending, dict):
            return None
        normalized = " ".join(user_input.strip().lower().split())
        if normalized not in NEGATIVE_GATEWAY_REPLIES:
            return None
        context_input = str(pending.get("context_input", "")).strip()
        if "/var/log" in context_input:
            return (
                "Understood. I won't delete logs under /var/log. "
                "If you still want to free space, tell me a safer, bounded cleanup scope."
            )
        return (
            "Understood. I won't do that. "
            "If you'd like, tell me a safer or more specific alternative."
        )
