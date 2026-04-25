from __future__ import annotations

from typing import Any

from rich.console import ConsoleRenderable, Group
from rich.panel import Panel
from rich.text import Text
from textual.widgets import Static

from xfusion.domain.enums import RiskLevel, StepStatus
from xfusion.domain.models.execution_plan import PlanStep

STATUS_STYLE = {
    StepStatus.PENDING: "dim",
    StepStatus.RUNNING: "yellow",
    StepStatus.SUCCESS: "green",
    StepStatus.FAILED: "red",
    StepStatus.SKIPPED: "blue",
    StepStatus.REFUSED: "red",
}

STATUS_SYMBOL = {
    StepStatus.PENDING: "○",
    StepStatus.RUNNING: "◆",
    StepStatus.SUCCESS: "●",
    StepStatus.FAILED: "×",
    StepStatus.SKIPPED: "◇",
    StepStatus.REFUSED: "!",
}


class StepWidget(Static):
    """Render one execution step as a compact timeline row or expanded panels."""

    def __init__(
        self,
        step: PlanStep,
        output: dict[str, Any] | None = None,
        *,
        debug: bool = False,
    ) -> None:
        super().__init__()
        self.step = step
        self.output = output
        self.debug = debug
        # Auto-expand if risk is medium/high or approval is pending
        self.expanded = self.step.risk_level in {RiskLevel.MEDIUM, RiskLevel.HIGH} or bool(
            self.step.approval_id
        )

    def on_click(self) -> None:
        """Toggle expanded state on click."""
        self.expanded = not self.expanded
        self.refresh()

    def render(self) -> ConsoleRenderable:
        if not self.expanded:
            return self._render_compact()
        return self._render_expanded()

    def _render_compact(self) -> Text:
        style = STATUS_STYLE.get(self.step.status, "")
        symbol = STATUS_SYMBOL.get(self.step.status, "•")
        risk = self._risk_label()
        approval = self._approval_label()

        result = Text()
        result.append(symbol, style=style)
        result.append(f" {self.step.status.value.upper()} ", style=f"bold {style}".strip())
        result.append(self.step.capability, style="bold")
        result.append(f"  risk={risk}", style="dim")
        result.append(f"  approval={approval}", style="dim")

        summary = str((self.output or {}).get("summary") or "").strip()
        if summary:
            result.append(f"\n  {summary}", style="dim")

        stdout = str((self.output or {}).get("stdout") or "").strip()
        if stdout and self.debug:
            result.append("\n  output: ", style="bold")
            result.append(stdout[:240], style="dim")

        if self.debug:
            self._append_debug_metadata(result)

        return result

    def _render_expanded(self) -> Group:
        # Step Panel
        step_text = Text()
        args_str = " ".join(f"{k}={v}" for k, v in self.step.args.items())
        cmd = f"{self.step.capability} {args_str}".strip()
        step_text.append("Command\n", style="bold")
        step_text.append(f"  {cmd}\n\n", style="cyan")

        output = (self.output or {}).get("stdout") or ""
        if output:
            step_text.append("Output\n", style="bold")
            step_text.append(f"  {str(output).strip()}\n\n", style="dim")

        interpretation = (self.output or {}).get("summary") or ""
        if interpretation:
            step_text.append("Interpretation\n", style="bold")
            step_text.append(f"  {str(interpretation).strip()}", style="green")

        step_panel = Panel(
            step_text,
            title=f"Step: {self.step.intent or self.step.capability}",
            title_align="left",
            border_style="white",
        )

        # Risk Gate Panel
        risk_text = Text()
        risk_label = self._risk_label()
        risk_text.append("Action: ", style="bold")
        risk_text.append(f"{self.step.capability}\n", style="yellow")
        risk_text.append("Risk: ", style="bold")
        risk_text.append(f"{risk_label}\n", style="red" if risk_label != "low" else "green")
        risk_text.append("Approval: ", style="bold")
        approval_style = "bold red" if self.step.approval_id else "green"
        risk_text.append(f"{self._approval_label()}", style=approval_style)

        risk_panel = Panel(
            risk_text,
            title="Risk Gate",
            title_align="left",
            border_style="red" if risk_label != "low" or self.step.approval_id else "green",
        )

        return Group(step_panel, risk_panel)

    def _risk_label(self) -> str:
        final_risk = self.step.final_risk_category or self.step.policy_category
        return final_risk.value if final_risk else "unknown"

    def _approval_label(self) -> str:
        if self.step.approved_action_hash:
            return "approved"
        if self.step.approval_id:
            return "requested"
        return "not-required"

    def _append_debug_metadata(self, result: Text) -> None:
        envelope = self.step.system_risk_envelope
        escalated = "yes" if envelope.get("escalated") else "no"
        policy_category = (
            self.step.policy_category.value if self.step.policy_category else "unknown"
        )
        final_risk = self._risk_label()
        args_str = ", ".join(f"{key}={value}" for key, value in self.step.args.items())

        result.append("\n  Runtime:", style="bold")
        result.append(
            "\n    "
            f"surface={self.step.execution_surface.value}  "
            f"policy={policy_category}  "
            f"final_risk={final_risk}  "
            f"escalated={escalated}  "
            f"approval={self._approval_label().replace('-', ' ')}",
            style="dim",
        )

        if self.step.fallback_reason:
            result.append("\n  Fallback:", style="bold")
            result.append(f"\n    {self.step.fallback_reason}", style="dim")

        fingerprint = self.step.resolution_record.get("raw_command_fingerprint")
        if fingerprint:
            result.append("\n  Fingerprint:", style="bold")
            result.append(f"\n    {fingerprint}", style="dim")

        result.append("\n  Request:", style="bold")
        command_text = (
            self.step.capability if not args_str else f"{self.step.capability} {args_str}"
        )
        result.append(f"\n    $ {command_text}", style="dim")

        for index, entry in enumerate(self.step.command_trace[-2:], start=1):
            result.append(f"\n  Trace {index}:", style="bold")
            argv = entry.get("ran_argv") or entry.get("planned_argv")
            if isinstance(argv, list):
                result.append("\n    argv=" + " ".join(str(part) for part in argv), style="dim")
            stdout = str(entry.get("stdout_excerpt") or "").strip()
            stderr = str(entry.get("stderr_excerpt") or "").strip()
            if stdout:
                result.append("\n    stdout: " + stdout[:240], style="dim")
            if stderr:
                result.append("\n    stderr: " + stderr[:240], style="dim red")
