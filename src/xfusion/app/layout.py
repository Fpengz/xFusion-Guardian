from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.widgets import Footer, Input, Label, RichLog, Static

from xfusion.app.widgets.palette import CommandPalette


def compose_main_layout() -> ComposeResult:
    yield Static("Initializing...", id="status-bar")
    yield VerticalScroll(id="timeline")
    yield CommandPalette(id="command-palette")
    with Horizontal(id="input-container"):
        yield Label("guardian >", id="prompt-label")
        yield Input(
            placeholder="Describe an operation or type / for commands",
            id="main-input",
        )
    with Vertical(id="sidebar"):
        yield Static("Environment", classes="sidebar-title")
        yield Static("", id="side-env")
        yield Static("\nAudit log", classes="sidebar-title")
        yield RichLog(id="side-audit", highlight=True, markup=True)
    yield Footer()
