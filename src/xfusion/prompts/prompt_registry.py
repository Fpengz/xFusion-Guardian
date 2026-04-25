from __future__ import annotations

from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError

PromptScope = Literal["global", "step", "capability", "risk", "user"]


class PromptRegistryError(ValueError):
    """Raised when prompt module loading or reload validation fails closed."""


class PromptModule(BaseModel):
    """One independently loadable prompt module."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1)
    scope: PromptScope
    applies_to: list[str] = Field(default_factory=list)
    priority: int
    enabled: bool
    version: str = Field(min_length=1)
    content: str = Field(min_length=1)
    tags: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class PromptRegistry:
    """Load, validate, and hot-reload prompt modules from YAML."""

    def __init__(
        self,
        prompts_root: str | Path | None = None,
        *,
        active_versions: dict[str, str] | None = None,
        allow_disable_required_safety: bool = False,
    ) -> None:
        self.prompts_root = Path(prompts_root).resolve() if prompts_root else None
        self.active_versions = dict(active_versions or {})
        self.allow_disable_required_safety = allow_disable_required_safety
        self._modules: list[PromptModule] = []
        self._snapshot: tuple[tuple[str, int, int], ...] = ()

    def load_all(self, path: str | Path | None = None) -> list[PromptModule]:
        root = Path(path).resolve() if path else self._require_root()
        modules, snapshot = self._load_modules(root)
        self.prompts_root = root
        self._modules = modules
        self._snapshot = snapshot
        return list(self._modules)

    def get_active_modules(self) -> list[PromptModule]:
        self._ensure_current()
        return [module for module in self._modules if self._is_active(module)]

    def get_all_modules(self) -> list[PromptModule]:
        self._ensure_current()
        return list(self._modules)

    def snapshot_descriptor(self) -> tuple[tuple[str, int, int], ...]:
        self._ensure_current()
        return self._snapshot

    def _ensure_current(self) -> None:
        root = self._require_root()
        live_snapshot = self._build_snapshot(root)
        if not self._modules or live_snapshot != self._snapshot:
            self.load_all(root)

    def _require_root(self) -> Path:
        if self.prompts_root is None:
            raise PromptRegistryError("prompt registry requires a prompts root before loading")
        return self.prompts_root

    def _load_modules(
        self,
        root: Path,
    ) -> tuple[list[PromptModule], tuple[tuple[str, int, int], ...]]:
        if not root.exists():
            raise PromptRegistryError(f"prompts root does not exist: {root}")

        paths = sorted(root.glob("**/*.yaml"))
        if not paths:
            raise PromptRegistryError(f"no prompt modules found under {root}")

        modules: list[PromptModule] = []
        errors: list[str] = []
        for path in paths:
            try:
                raw = yaml.safe_load(path.read_text(encoding="utf-8"))
                module = PromptModule.model_validate(raw)
                modules.append(module)
            except (OSError, ValidationError, yaml.YAMLError) as exc:
                errors.append(f"{path}: {exc}")

        if errors:
            raise PromptRegistryError("; ".join(errors))

        self._validate_modules(modules)
        return modules, self._build_snapshot(root)

    def _validate_modules(self, modules: list[PromptModule]) -> None:
        seen: set[tuple[str, str]] = set()
        enabled_by_id: dict[str, list[PromptModule]] = {}
        for module in modules:
            key = (module.id, module.version)
            if key in seen:
                raise PromptRegistryError(
                    f"duplicate prompt module version detected for {module.id}:{module.version}"
                )
            seen.add(key)
            if module.enabled:
                enabled_by_id.setdefault(module.id, []).append(module)

        for module_id, enabled_versions in enabled_by_id.items():
            if len(enabled_versions) > 1 and module_id not in self.active_versions:
                versions = ", ".join(sorted(module.version for module in enabled_versions))
                raise PromptRegistryError(
                    f"multiple enabled versions detected for prompt module {module_id}: {versions}"
                )

        required_safety = [
            module
            for module in modules
            if module.scope == "global" and {"required", "safety"} <= set(module.tags)
        ]
        if not required_safety:
            raise PromptRegistryError("required global safety prompt module is missing")

        if not self.allow_disable_required_safety and any(
            not module.enabled for module in required_safety
        ):
            raise PromptRegistryError(
                "required global safety prompt modules cannot be disabled without override"
            )

        if not any(self._is_active(module) for module in required_safety):
            raise PromptRegistryError("required global safety prompt module is not active")

    def _is_active(self, module: PromptModule) -> bool:
        if not module.enabled:
            return False
        selected_version = self.active_versions.get(module.id)
        return selected_version is None or selected_version == module.version

    def _build_snapshot(self, root: Path) -> tuple[tuple[str, int, int], ...]:
        snapshot: list[tuple[str, int, int]] = []
        for path in sorted(root.glob("**/*.yaml")):
            stat = path.stat()
            snapshot.append((str(path.relative_to(root)), stat.st_mtime_ns, stat.st_size))
        return tuple(snapshot)
