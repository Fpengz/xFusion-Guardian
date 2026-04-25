from __future__ import annotations

from xfusion.app.commands.base import BaseCommand


class CommandRegistry:
    """Manages discovery and execution of commands."""

    def __init__(self):
        self.commands: dict[str, BaseCommand] = {}
        self.alias_map: dict[str, str] = {}

    def register(self, command: BaseCommand):
        """Register a command and its aliases."""
        self.commands[command.name] = command
        for alias in command.aliases:
            self.alias_map[alias] = command.name

    def find(self, trigger: str) -> BaseCommand | None:
        """Find a command by name or alias."""
        # Remove leading slash if present for lookup
        trigger = trigger.lstrip("/")
        name = self.alias_map.get(trigger, trigger)
        return self.commands.get(name)

    def search(self, query: str) -> list[BaseCommand]:
        """Fuzzy search commands by name or alias."""
        query = query.lstrip("/").lower()
        results = []
        for cmd in self.commands.values():
            if query in cmd.name.lower() or any(query in a.lower() for a in cmd.aliases):
                results.append(cmd)
        return results

    def get_all(self) -> list[BaseCommand]:
        """Return all registered commands."""
        return list(self.commands.values())
