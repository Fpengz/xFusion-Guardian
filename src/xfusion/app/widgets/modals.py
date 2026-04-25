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
            yield Label(
                "[dim]Paste/type the phrase, then press Enter. Esc cancels.[/]",
                id="approval-help",
            )

    def on_mount(self) -> None:
        self.query_one("#approval-input", Input).focus()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        phrase = event.value.strip()
        if not phrase:
            self.query_one("#approval-help", Label).update(
                "[dim]Paste/type the phrase above, then press Enter. Esc cancels.[/]"
            )
            return
        self.dismiss(phrase)

    def on_key(self, event) -> None:
        if event.key == "escape":
            self.dismiss(None)
