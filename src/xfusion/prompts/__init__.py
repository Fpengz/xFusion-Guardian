from __future__ import annotations

from pathlib import Path

from xfusion.prompts.prompt_composer import PromptBuildError, PromptBuildResult, compose_prompt
from xfusion.prompts.prompt_registry import PromptModule, PromptRegistry, PromptRegistryError
from xfusion.prompts.prompt_selector import PromptContext, PromptSelectionResult, select_modules


def default_prompts_root() -> Path:
    return Path(__file__).resolve().parents[3] / "prompts"


def capability_prompt_module(
    capability_name: str,
    *,
    instructions: str,
    constraints: list[str],
    priority: int = 0,
) -> PromptModule:
    content = instructions.strip()
    if constraints:
        content += "\nConstraints:\n" + "\n".join(f"- {constraint}" for constraint in constraints)
    return PromptModule(
        id=f"capability::{capability_name}",
        scope="capability",
        applies_to=[capability_name],
        priority=priority,
        enabled=True,
        version="manifest",
        content=content,
        tags=[],
        metadata={"capability_name": capability_name, "source": "capability_manifest"},
    )


def build_prompt(
    *,
    ctx: PromptContext,
    prompts_root: str | Path | None = None,
    registry: PromptRegistry | None = None,
    capability_modules: list[PromptModule] | None = None,
    extra_why_selected: list[str] | None = None,
    extra_rejected: list[dict[str, object]] | None = None,
) -> PromptBuildResult:
    prompt_registry = registry or PromptRegistry(prompts_root or default_prompts_root())
    try:
        modules = prompt_registry.get_all_modules()
    except PromptRegistryError:
        reload_root = prompts_root or prompt_registry.prompts_root or default_prompts_root()
        modules = prompt_registry.load_all(reload_root)

    selection = select_modules(
        ctx,
        modules,
        active_versions=prompt_registry.active_versions,
    )
    selected_modules = list(selection.selected_modules)
    if capability_modules:
        for module in capability_modules:
            selected_modules.append(module)
            selection.why_selected.append(
                "Selected because capability manifest prompt for "
                f"'{module.applies_to[0]}' is active."
            )

    rejected = list(selection.rejected_modules)
    if extra_rejected:
        rejected.extend(extra_rejected)
    why_selected = list(selection.why_selected)
    if extra_why_selected:
        why_selected.extend(extra_why_selected)
    return compose_prompt(
        selected_modules,
        rejected_modules=rejected,
        why_selected=why_selected,
    )


__all__ = [
    "PromptBuildError",
    "PromptBuildResult",
    "PromptContext",
    "PromptModule",
    "PromptRegistry",
    "PromptRegistryError",
    "PromptSelectionResult",
    "build_prompt",
    "capability_prompt_module",
    "compose_prompt",
    "default_prompts_root",
    "select_modules",
]
