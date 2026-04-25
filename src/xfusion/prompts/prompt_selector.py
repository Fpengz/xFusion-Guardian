from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from xfusion.prompts.prompt_registry import PromptModule

PromptStepType = Literal["planning", "execution", "verification"]
PromptRiskLevel = Literal["low", "medium", "high"]

SECTION_ORDER = {
    "global": 0,
    "step": 1,
    "capability": 2,
    "risk": 3,
    "user": 4,
}


class PromptContext(BaseModel):
    """Deterministic prompt selection context."""

    model_config = ConfigDict(extra="forbid")

    step_type: PromptStepType
    capability: str | None = None
    risk_level: PromptRiskLevel
    project_context: dict[str, Any] = Field(default_factory=dict)


class PromptSelectionResult(BaseModel):
    """Explainable prompt selection output."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    selected_modules: list[PromptModule] = Field(default_factory=list)
    rejected_modules: list[dict[str, object]] = Field(default_factory=list)
    why_selected: list[str] = Field(default_factory=list)


def select_modules(
    ctx: PromptContext,
    modules: list[PromptModule],
    *,
    active_versions: dict[str, str] | None = None,
) -> PromptSelectionResult:
    """Select prompt modules deterministically with explicit rejection reasons."""
    active_versions = dict(active_versions or {})
    selected: list[PromptModule] = []
    rejected: list[dict[str, object]] = []
    why_selected: list[str] = []

    for module in sorted(modules, key=_sort_key):
        rejection_reason = _rejection_reason(module, ctx, active_versions)
        if rejection_reason is not None:
            rejected.append(
                {
                    "module_id": module.id,
                    "version": module.version,
                    "scope": module.scope,
                    "reason": rejection_reason,
                }
            )
            continue

        selected.append(module)
        why_selected.append(_why_selected(module, ctx))

    return PromptSelectionResult(
        selected_modules=selected,
        rejected_modules=rejected,
        why_selected=why_selected,
    )


def _sort_key(module: PromptModule) -> tuple[int, int, str, str]:
    return (SECTION_ORDER[module.scope], -module.priority, module.id, module.version)


def _rejection_reason(
    module: PromptModule,
    ctx: PromptContext,
    active_versions: dict[str, str],
) -> str | None:
    if not module.enabled:
        if module.scope == "global" and {"required", "safety"} <= set(module.tags):
            return "required_safety_disabled"
        return "disabled"

    selected_version = active_versions.get(module.id)
    if selected_version is not None and module.version != selected_version:
        return "version_override_mismatch"

    if module.scope == "global":
        return None
    if module.scope == "step":
        return None if ctx.step_type in module.applies_to else "scope_mismatch"
    if module.scope == "capability":
        return None if ctx.capability and ctx.capability in module.applies_to else "target_mismatch"
    if module.scope == "risk":
        return None if ctx.risk_level in module.applies_to else "target_mismatch"
    if module.scope == "user":
        return (
            None
            if _matches_project_context(module.applies_to, ctx.project_context)
            else "target_mismatch"
        )
    return "scope_mismatch"


def _matches_project_context(applies_to: list[str], project_context: dict[str, Any]) -> bool:
    if not applies_to:
        return False
    for value in project_context.values():
        if isinstance(value, str) and value in applies_to:
            return True
        if isinstance(value, list) and any(
            isinstance(item, str) and item in applies_to for item in value
        ):
            return True
    return False


def _why_selected(module: PromptModule, ctx: PromptContext) -> str:
    if module.scope == "global":
        return f"Selected because global module {module.id} is always included."
    if module.scope == "step":
        return (
            f"Selected because step_type '{ctx.step_type}' exactly matched step module {module.id}."
        )
    if module.scope == "capability":
        return (
            f"Selected because capability '{ctx.capability}' exactly matched "
            f"capability module {module.id}."
        )
    if module.scope == "risk":
        return (
            f"Selected because risk_level '{ctx.risk_level}' exactly matched "
            f"risk module {module.id}."
        )
    return f"Selected because project context exactly matched user module {module.id}."
