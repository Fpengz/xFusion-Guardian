from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from xfusion.app.tui import XFusionTUI


class BaseCommand(ABC):
    """Abstract base class for all slash commands."""

    name: str
    aliases: list[str] = []
    description: str
    usage: str
    is_client_only: bool = True
    mutates_session_state: bool = False

    @abstractmethod
    async def handle(self, app: XFusionTUI, args: list[str]) -> None:
        """Logic for executing the command."""
        pass
