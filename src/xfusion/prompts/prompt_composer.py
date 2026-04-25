from __future__ import annotations

import hashlib
import json

from pydantic import BaseModel, ConfigDict, Field

from xfusion.prompts.prompt_registry import PromptModule
from xfusion.prompts.prompt_selector import SECTION_ORDER


class PromptBuildError(ValueError):
    """Raised when prompt composition fails closed."""


class PromptBuildResult(BaseModel):
    """Structured prompt output plus explainability metadata."""

    model_config = ConfigDict(extra="forbid")

    system_prompt: str = Field(min_length=1)
    selected_modules: list[dict[str, object]] = Field(default_factory=list)
    rejected_modules: list[dict[str, object]] = Field(default_factory=list)
    why_selected: list[str] = Field(default_factory=list)
    final_sections: list[str] = Field(default_factory=list)
    snapshot_hash: str = Field(min_length=1)


def compose_prompt(
    modules: list[PromptModule],
    *,
    rejected_modules: list[dict[str, object]] | None = None,
    why_selected: list[str] | None = None,
) -> PromptBuildResult:
    """Compose selected modules into a stable, sectioned system prompt."""
    ordered_modules = sorted(
        modules,
        key=lambda module: (
            SECTION_ORDER[module.scope],
            -module.priority,
            module.id,
            module.version,
        ),
    )

    if not any(
        module.scope == "global" and {"required", "safety"} <= set(module.tags)
        for module in ordered_modules
    ):
        raise PromptBuildError("GLOBAL SAFETY section requires at least one required safety module")

    section_content: dict[str, list[str]] = {}
    for module in ordered_modules:
        header = _section_header(module)
        section_content.setdefault(header, []).append(module.content.strip())

    if "[GLOBAL SAFETY]" not in section_content:
        raise PromptBuildError("GLOBAL SAFETY section is required")

    final_sections = list(section_content)
    if not final_sections:
        raise PromptBuildError("final system prompt cannot be empty")

    rendered_sections = []
    for header, parts in section_content.items():
        body = "\n\n".join(part for part in parts if part)
        if not body:
            continue
        rendered_sections.append(f"{header}\n{body}")

    system_prompt = "\n\n".join(rendered_sections).strip()
    if not system_prompt:
        raise PromptBuildError("final system prompt cannot be empty")

    snapshot_payload = {
        "system_prompt": system_prompt,
        "selected_modules": [module.model_dump() for module in ordered_modules],
        "rejected_modules": rejected_modules or [],
        "final_sections": final_sections,
    }
    snapshot_hash = hashlib.sha256(
        json.dumps(snapshot_payload, sort_keys=True).encode("utf-8")
    ).hexdigest()

    return PromptBuildResult(
        system_prompt=system_prompt,
        selected_modules=[module.model_dump() for module in ordered_modules],
        rejected_modules=rejected_modules or [],
        why_selected=why_selected or [],
        final_sections=[header.strip("[]") for header in final_sections],
        snapshot_hash=snapshot_hash,
    )


def _section_header(module: PromptModule) -> str:
    if module.scope == "global":
        return "[GLOBAL SAFETY]"
    if module.scope == "step":
        step = module.applies_to[0] if module.applies_to else "planning"
        role = {
            "planning": "PLANNER",
            "execution": "EXECUTOR",
            "verification": "VERIFIER",
        }.get(step, step.upper())
        return f"[ROLE: {role}]"
    if module.scope == "capability":
        capability_name = str(module.metadata.get("capability_name") or module.applies_to[0])
        return f"[CAPABILITY: {capability_name}]"
    if module.scope == "risk":
        return "[RISK CONTROL]"
    return "[PROJECT CONTEXT]"
