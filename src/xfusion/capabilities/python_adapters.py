from __future__ import annotations

from collections.abc import Callable
from typing import Any

from xfusion.tools.base import ToolOutput

PythonAdapter = Callable[..., ToolOutput]


class PythonAdapterRegistryError(KeyError):
    """Raised when a python adapter is required but not reviewed and bound."""


class PythonAdapterRegistry:
    """Reviewed Python adapter registry for v0.2.5 catalog manifests."""

    def __init__(
        self,
        adapters: dict[str, PythonAdapter],
        *,
        allow_unavailable_adapters: bool = False,
    ) -> None:
        self._adapters = dict(adapters)
        self.allow_unavailable_adapters = allow_unavailable_adapters

    def has(self, adapter_id: str) -> bool:
        return adapter_id in self._adapters

    def require(self, adapter_id: str) -> PythonAdapter:
        adapter = self._adapters.get(adapter_id)
        if adapter is None:
            raise PythonAdapterRegistryError(f"unbound python adapter: {adapter_id}")
        return adapter

    def execute(self, adapter_id: str, args: dict[str, Any]) -> ToolOutput:
        adapter = self._adapters.get(adapter_id)
        if adapter is None:
            if self.allow_unavailable_adapters:
                return ToolOutput(
                    summary="Python adapter is not implemented.",
                    data={
                        "status": "unavailable",
                        "summary": "Python adapter is not implemented.",
                        "unavailable_reason": "unbound_adapter",
                    },
                )
            raise PythonAdapterRegistryError(f"unbound python adapter: {adapter_id}")
        return adapter(**args)

    def unavailable_adapter_ids(self, adapter_ids: set[str]) -> set[str]:
        return {adapter_id for adapter_id in adapter_ids if adapter_id not in self._adapters}
