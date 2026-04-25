from __future__ import annotations

from rich.text import Text
from textual.containers import VerticalScroll
from textual.widgets import Static

from xfusion.app.commands.base import BaseCommand


class CommandItem(Static):
    """A single command entry in the palette."""

    def __init__(self, command: BaseCommand):
        super().__init__()
        self.command = command

    def render(self) -> Text:
        result = Text()
        result.append(f"/{self.command.name}", style="bold")
        if self.command.aliases:
            aliases = ", ".join(f"/{alias}" for alias in self.command.aliases)
            result.append(f" ({aliases})", style="dim")
        result.append(f"  {self.command.description}", style="italic")
        return result


class CommandPalette(VerticalScroll):
    """Floating slash-command palette."""

    DEFAULT_CSS = """
    CommandPalette {
        display: none;
        background: $surface;
        border: tall $border;
        height: auto;
        max-height: 10;
        width: 84;
        dock: bottom;
        margin-bottom: 3;
        margin-left: 2;
        padding: 0 1;
    }

    CommandPalette CommandItem {
        padding: 0 1;
        color: $text-muted;
    }

    CommandPalette CommandItem:hover {
        background: $boost;
    }

    CommandPalette .selected {
        background: $accent;
        color: $text;
        text-style: bold;
    }
    """

    def move_selection(self, direction: int) -> None:
        items = self.query(CommandItem)
        if not items:
            return

        current_index = -1
        for index, item in enumerate(items):
            if item.has_class("selected"):
                current_index = index
                item.remove_class("selected")
                break

        new_index = (current_index + direction) % len(items)
        items[new_index].add_class("selected")
        items[new_index].scroll_visible()

    def get_selected(self) -> BaseCommand | None:
        for item in self.query(CommandItem):
            if item.has_class("selected"):
                return item.command
        return None
