from __future__ import annotations

from pathlib import Path


class ExecutableRegistryError(ValueError):
    """Raised when the executable allowlist is malformed or violated."""


class ExecutableRegistry:
    """Global executable allowlist for v0.2.5 argv-backed capabilities."""

    def __init__(self, executables: dict[str, str]) -> None:
        errors: list[str] = []
        normalized: dict[str, str] = {}
        for executable_id, raw_path in executables.items():
            if not executable_id or not isinstance(executable_id, str):
                errors.append("executable id must be a non-empty string")
                continue
            path = Path(raw_path)
            if not path.is_absolute():
                errors.append(f"{executable_id}: executable path must be absolute")
                continue
            if any(part in {"", ".", ".."} for part in path.parts[1:]):
                errors.append(f"{executable_id}: executable path must be normalized")
                continue
            normalized[executable_id] = str(path)
        if errors:
            raise ExecutableRegistryError("; ".join(errors))
        self._executables = normalized

    def has(self, executable_id: str) -> bool:
        return executable_id in self._executables

    def require(self, executable_id: str) -> str:
        try:
            return self._executables[executable_id]
        except KeyError as exc:
            raise ExecutableRegistryError(f"unknown executable id '{executable_id}'") from exc

    def all(self) -> dict[str, str]:
        return dict(self._executables)
