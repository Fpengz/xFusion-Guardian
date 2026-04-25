from __future__ import annotations

from typing import Any

from rich.markdown import Markdown
from rich.panel import Panel
from rich.text import Text
from textual.app import ComposeResult
from textual.containers import Vertical
from textual.widgets import Label, Static

from xfusion.app.widgets.steps import StepWidget
from xfusion.domain.enums import InteractionState
from xfusion.domain.models.execution_plan import ExecutionPlan


class UserMessage(Static):
    """Compact renderable for user turns."""

    def __init__(self, text: str) -> None:
        super().__init__(f"> {text}", classes="user-message", markup=False)


class TaskWidget(Static):
    """Render the main execution goal as a Task panel."""

    def __init__(self, goal: str) -> None:
        super().__init__(id="task-widget")
        self.goal = goal

    def render(self) -> Panel:
        return Panel(self.goal, title="Task", title_align="left", border_style="blue")


class PlanWidget(Static):
    """Render the execution plan steps as a Plan panel."""

    def __init__(self, plan: ExecutionPlan | None = None) -> None:
        super().__init__(id="plan-widget")
        self.plan = plan

    def render(self) -> Panel | Text:
        if not self.plan:
            return Text("")
        text = Text()
        for idx, step in enumerate(self.plan.steps, start=1):
            text.append(f"{idx}. {step.intent}\n")
        return Panel(text, title="Plan", title_align="left", border_style="cyan")


class AgentMessage(Static):
    """Structured block for an agent response turn."""

    def __init__(self, state: dict[str, Any]):
        super().__init__()
        self.state = state
        self.turn_header = Label("Guardian", id="turn-header")
        self.task_widget = TaskWidget("")
        self.plan_widget = PlanWidget(None)
        self.steps_container = Vertical(id="steps")
        self.policy_label = Static("", id="policy-info", markup=False)
        self.explanation_container = Vertical(
            Label("", id="interpretation-header"),
            Static("", id="explanation"),
            id="explanation-block",
        )
        self.debug_container = Vertical(id="debug-info")

    def compose(self) -> ComposeResult:
        yield self.turn_header
        yield self.task_widget
        yield self.plan_widget
        yield self.steps_container
        yield self.policy_label
        yield self.explanation_container
        yield self.debug_container

    def update_state(self, state: dict[str, Any]) -> None:
        self.state = state
        plan = state.get("plan")
        mode = state.get("response_mode", "normal")
        gateway_mode = state.get("gateway_mode")
        debug = mode == "debug"

        self.turn_header.update(self._turn_title(state))

        if gateway_mode in {"conversational", "clarify"}:
            self.task_widget.display = False
            self.plan_widget.display = False
        elif isinstance(plan, ExecutionPlan):
            self.task_widget.goal = plan.goal
            self.task_widget.display = True
            self.plan_widget.plan = plan
            self.plan_widget.display = True
        else:
            self.task_widget.display = False
            self.plan_widget.display = False

        self.steps_container.remove_children()
        if not gateway_mode and isinstance(plan, ExecutionPlan):
            step_outputs = state.get("step_outputs", {})
            for step in plan.steps:
                output = step_outputs.get(step.step_id)
                self.steps_container.mount(StepWidget(step, output, debug=debug))

        explanation_label = self.explanation_container.query_one("#explanation", Static)
        header_label = self.explanation_container.query_one("#interpretation-header", Label)
        response = state.get("response")
        if response:
            self.explanation_container.display = True
            header = self._response_header(gateway_mode, plan)
            header_label.update(header)
            header_label.display = bool(header)
            explanation_label.update(Markdown(response))
        else:
            self.explanation_container.display = False

        decision = state.get("policy_decision")
        if not gateway_mode and decision and debug:
            self.policy_label.update(self._format_policy_decision(decision))
            self.policy_label.display = True
        else:
            self.policy_label.display = False

        self.debug_container.remove_children()
        self.debug_container.display = debug
        if debug and not gateway_mode:
            audit_records = state.get("audit_records", [])
            if audit_records:
                self.debug_container.mount(Label("Audit trace", classes="debug-header"))
                for rec in audit_records[-5:]:
                    msg = rec.get("message", str(rec))
                    self.debug_container.mount(self._debug_line_widget(str(msg)))
        if debug:
            for widget in self._debug_log_widgets(state):
                self.debug_container.mount(widget)

    def _turn_title(self, state: dict[str, Any]) -> str:
        gateway_mode = state.get("gateway_mode")
        if gateway_mode == "clarify":
            return "Guardian · clarification"
        if gateway_mode == "conversational":
            return "Guardian · response"
        return "Guardian · execution"

    def _response_header(self, gateway_mode: Any, plan: Any) -> str:
        if gateway_mode == "clarify":
            return "Action required"
        if gateway_mode == "conversational":
            return ""
        if plan and plan.interaction_state == InteractionState.COMPLETED:
            return "Summary"
        return "Status"

    def _debug_log_widgets(self, state: dict[str, Any]) -> list[Static | Label]:
        logs = state.get("debug_logs", [])
        if not isinstance(logs, list) or not logs:
            return []
        widgets: list[Static | Label] = [Label("Debug Logs:", classes="debug-header")]
        for line in logs[-12:]:
            widgets.append(self._debug_line_widget(str(line)))
        return widgets

    def _debug_line_widget(self, line: str) -> Static:
        return Static(f"• {line}", classes="debug-entry", markup=False)

    def _format_policy_decision(self, decision: Any) -> str:
        decision_value = getattr(getattr(decision, "decision", None), "value", None) or str(
            getattr(decision, "decision", "unknown")
        )
        surface = getattr(getattr(decision, "execution_surface", None), "value", None) or str(
            getattr(decision, "execution_surface", "unknown")
        )
        category = getattr(getattr(decision, "policy_category", None), "value", None) or str(
            getattr(decision, "policy_category", "unknown")
        )
        approval = getattr(getattr(decision, "approval_mode", None), "value", None) or str(
            getattr(decision, "approval_mode", "unknown")
        )
        rule = str(getattr(decision, "matched_rule_id", "unknown"))
        reason = str(getattr(decision, "reason_text", "")).strip()
        lines = [
            "Policy Decision:",
            f"  decision={decision_value}  surface={surface}  category={category}",
            f"  rule={rule}  approval={approval}",
        ]
        if reason:
            lines.append(f"  reason={reason}")
        return "\n".join(lines)
