from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import Input, Label


class ApprovalModal(ModalScreen[str]):
    """Modal screen for capturing explicit approval phrases."""

    DEFAULT_CSS = """
    ApprovalModal {
        align: center middle;
    }

    #modal-content {
        width: 62;
        height: auto;
        background: $surface;
        border: tall $warning;
        padding: 1 2;
    }

    #modal-content Label {
        text-align: center;
        width: 100%;
        margin-bottom: 1;
    }

    #approval-phrase {
        color: $error;
        text-style: bold reverse;
    }

    #approval-input {
        margin-top: 1;
        border: none;
        background: transparent;
    }

    #approval-input:focus {
        background: $boost;
    }
    """

    def __init__(self, phrase: str):
        super().__init__()
        self.phrase = phrase

    def compose(self) -> ComposeResult:
        with Vertical(id="modal-content"):
            yield Label("Approval required")
            yield Label("This operation needs an explicit confirmation phrase.")
            yield Label("Type exactly:")
            yield Label(f" {self.phrase} ", id="approval-phrase")
            yield Input(placeholder="Confirmation phrase", id="approval-input")
            yield Label("[dim]Esc cancels[/]")

    def on_input_submitted(self, event: Input.Submitted) -> None:
        self.dismiss(event.value)

    def on_key(self, event) -> None:
        if event.key == "escape":
            self.dismiss(None)
