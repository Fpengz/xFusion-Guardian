from __future__ import annotations

from pathlib import Path

import pytest

from xfusion.capabilities.registry import CapabilityRegistry
from xfusion.capabilities.resolver import resolve_intent_to_capability
from xfusion.domain.enums import ApprovalMode, RiskTier
from xfusion.domain.models.capability import (
    CapabilityDefinition,
    CapabilityPrompt,
    RuntimeConstraints,
)
from xfusion.prompts.prompt_composer import (
    PromptBuildError,
    compose_prompt,
)
from xfusion.prompts.prompt_registry import (
    PromptModule,
    PromptRegistry,
    PromptRegistryError,
)
from xfusion.prompts.prompt_selector import PromptContext, select_modules


def _write_module(root: Path, relative_path: str, body: str) -> Path:
    path = root / relative_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")
    return path


def _registry_with_disk_capability() -> CapabilityRegistry:
    return CapabilityRegistry(
        [
            CapabilityDefinition(
                name="system_inspection.check_disk_usage",
                version=1,
                verb="inspect",
                object="disk_usage",
                risk_tier=RiskTier.TIER_0,
                approval_mode=ApprovalMode.AUTO,
                allowed_environments=["dev", "staging", "production"],
                allowed_actor_types=["operator", "assistant"],
                scope_model={},
                input_schema={
                    "type": "object",
                    "required": ["path"],
                    "properties": {"path": {"type": "string", "minLength": 1}},
                    "additionalProperties": False,
                },
                output_schema={
                    "type": "object",
                    "required": ["usage_percent"],
                    "properties": {
                        "usage_percent": {"type": "integer", "minimum": 0, "maximum": 100}
                    },
                    "additionalProperties": False,
                },
                runtime_constraints=RuntimeConstraints(),
                adapter_id="argv:coreutils.df",
                is_read_only=True,
                preview_builder="default",
                verification_recommendation="output_check",
                redaction_policy="standard",
                short_description="Inspect filesystem usage for a validated path.",
                target_constraints={},
                execution_binding={},
                verification={"type": "output_check"},
                side_effect_classification="none",
                prompt=CapabilityPrompt(
                    instructions="Inspect only the validated path and report structured facts.",
                    constraints=[
                        "Do not infer filesystem state not present in normalized output.",
                    ],
                ),
            )
        ]
    )


class FakeResolverLLM:
    def __init__(self, response: str) -> None:
        self.response = response
        self.calls: list[tuple[str, str]] = []

    def complete(self, system_prompt: str, user_prompt: str, timeout: float = 20.0) -> str:
        self.calls.append((system_prompt, user_prompt))
        return self.response


def test_prompt_registry_loads_active_modules_and_hot_reloads_on_file_change(
    tmp_path: Path,
) -> None:
    prompts_root = tmp_path / "prompts"
    _write_module(
        prompts_root,
        "global/safety_guard.yaml",
        """
id: safety_guard
scope: global
applies_to: []
priority: 100
enabled: true
version: v1
content: Never bypass deterministic policy.
tags: [required, safety]
metadata: {}
""",
    )
    planner_path = _write_module(
        prompts_root,
        "step/planner.yaml",
        """
id: planner_role
scope: step
applies_to: [planning]
priority: 40
enabled: true
version: v1
content: Plan only. Do not execute.
tags: []
metadata: {}
""",
    )

    registry = PromptRegistry()
    loaded = registry.load_all(str(prompts_root))

    assert {module.id for module in loaded} == {"safety_guard", "planner_role"}
    assert {module.id for module in registry.get_active_modules()} == {
        "safety_guard",
        "planner_role",
    }

    planner_path.write_text(
        """
id: planner_role
scope: step
applies_to: [planning]
priority: 40
enabled: true
version: v1
content: Decompose only. Never act.
tags: []
metadata: {}
""",
        encoding="utf-8",
    )

    active = registry.get_active_modules()
    planner = next(module for module in active if module.id == "planner_role")
    assert planner.content == "Decompose only. Never act."


def test_prompt_registry_fails_closed_on_invalid_yaml_and_missing_required_safety(
    tmp_path: Path,
) -> None:
    prompts_root = tmp_path / "prompts"
    _write_module(
        prompts_root,
        "step/planner.yaml",
        """
id: planner_role
scope: step
applies_to: [planning]
priority: 40
enabled: true
version: v1
content: Plan only. Do not execute.
tags: []
metadata: {}
""",
    )

    registry = PromptRegistry()
    with pytest.raises(PromptRegistryError, match="required global safety"):
        registry.load_all(str(prompts_root))

    _write_module(
        prompts_root,
        "global/safety_guard.yaml",
        """
id: safety_guard
scope: global
applies_to: []
priority: 100
enabled: true
version: v1
content: Never bypass deterministic policy.
tags: [required, safety]
metadata: {}
""",
    )
    _write_module(
        prompts_root,
        "risk/bad.yaml",
        """
id: broken
scope risk
""",
    )

    with pytest.raises(PromptRegistryError):
        registry.load_all(str(prompts_root))


def test_prompt_registry_rejects_multiple_enabled_versions_without_override(
    tmp_path: Path,
) -> None:
    prompts_root = tmp_path / "prompts"
    _write_module(
        prompts_root,
        "global/safety_guard.yaml",
        """
id: safety_guard
scope: global
applies_to: []
priority: 100
enabled: true
version: v1
content: Never bypass deterministic policy.
tags: [required, safety]
metadata: {}
""",
    )
    _write_module(
        prompts_root,
        "step/planner_v1.yaml",
        """
id: planner_role
scope: step
applies_to: [planning]
priority: 40
enabled: true
version: v1
content: Plan only.
tags: []
metadata: {}
""",
    )
    _write_module(
        prompts_root,
        "step/planner_v2.yaml",
        """
id: planner_role
scope: step
applies_to: [planning]
priority: 45
enabled: true
version: v2
content: Decompose only.
tags: []
metadata: {}
""",
    )

    with pytest.raises(PromptRegistryError, match="multiple enabled versions"):
        PromptRegistry().load_all(str(prompts_root))


def test_select_modules_matches_scope_priority_and_records_rejections() -> None:
    modules = [
        PromptModule(
            id="safety_guard",
            scope="global",
            applies_to=[],
            priority=100,
            enabled=True,
            version="v1",
            content="Never bypass deterministic policy.",
            tags=["required", "safety"],
            metadata={},
        ),
        PromptModule(
            id="planner_role",
            scope="step",
            applies_to=["planning"],
            priority=40,
            enabled=True,
            version="v1",
            content="Plan only.",
            tags=[],
            metadata={},
        ),
        PromptModule(
            id="resolver_target",
            scope="user",
            applies_to=["resolver"],
            priority=30,
            enabled=True,
            version="v1",
            content="Use resolver response format.",
            tags=[],
            metadata={},
        ),
        PromptModule(
            id="gateway_target",
            scope="user",
            applies_to=["gateway"],
            priority=35,
            enabled=False,
            version="v1",
            content="Use gateway response format.",
            tags=[],
            metadata={},
        ),
        PromptModule(
            id="high_risk",
            scope="risk",
            applies_to=["high"],
            priority=50,
            enabled=True,
            version="v1",
            content="Require explicit confirmation language.",
            tags=[],
            metadata={},
        ),
    ]

    result = select_modules(
        PromptContext(
            step_type="planning",
            capability=None,
            risk_level="high",
            project_context={"prompt_targets": ["resolver"]},
        ),
        modules,
    )

    assert [module.id for module in result.selected_modules] == [
        "safety_guard",
        "planner_role",
        "high_risk",
        "resolver_target",
    ]
    assert any(item["module_id"] == "gateway_target" for item in result.rejected_modules)
    assert any("Selected because" in item for item in result.why_selected)


def test_compose_prompt_renders_stable_sections_without_duplicate_headers() -> None:
    modules = [
        PromptModule(
            id="safety_guard",
            scope="global",
            applies_to=[],
            priority=100,
            enabled=True,
            version="v1",
            content="Never bypass deterministic policy.",
            tags=["required", "safety"],
            metadata={},
        ),
        PromptModule(
            id="planner_role",
            scope="step",
            applies_to=["planning"],
            priority=40,
            enabled=True,
            version="v1",
            content="Plan only. Do not execute.",
            tags=[],
            metadata={},
        ),
        PromptModule(
            id="capability_prompt",
            scope="capability",
            applies_to=["system_inspection.check_disk_usage"],
            priority=20,
            enabled=True,
            version="v1",
            content="Inspect only the validated path.",
            tags=[],
            metadata={"capability_name": "system_inspection.check_disk_usage"},
        ),
        PromptModule(
            id="resolver_target",
            scope="user",
            applies_to=["resolver"],
            priority=10,
            enabled=True,
            version="v1",
            content="Return only JSON.",
            tags=[],
            metadata={},
        ),
    ]

    result = compose_prompt(modules)

    assert "[GLOBAL SAFETY]" in result.system_prompt
    assert "[ROLE: PLANNER]" in result.system_prompt
    assert "[CAPABILITY: system_inspection.check_disk_usage]" in result.system_prompt
    assert "[PROJECT CONTEXT]" in result.system_prompt
    assert result.system_prompt.count("[GLOBAL SAFETY]") == 1
    assert result.final_sections == [
        "GLOBAL SAFETY",
        "ROLE: PLANNER",
        "CAPABILITY: system_inspection.check_disk_usage",
        "PROJECT CONTEXT",
    ]


def test_compose_prompt_fails_closed_when_no_global_safety_module() -> None:
    modules = [
        PromptModule(
            id="planner_role",
            scope="step",
            applies_to=["planning"],
            priority=40,
            enabled=True,
            version="v1",
            content="Plan only. Do not execute.",
            tags=[],
            metadata={},
        )
    ]

    with pytest.raises(PromptBuildError, match="GLOBAL SAFETY"):
        compose_prompt(modules)


def test_resolver_returns_prompt_explainability_and_structured_prompt(tmp_path: Path) -> None:
    prompts_root = tmp_path / "prompts"
    _write_module(
        prompts_root,
        "global/safety_guard.yaml",
        """
id: safety_guard
scope: global
applies_to: []
priority: 100
enabled: true
version: v1
content: Never bypass deterministic policy.
tags: [required, safety]
metadata: {}
""",
    )
    _write_module(
        prompts_root,
        "step/planner.yaml",
        """
id: planner_role
scope: step
applies_to: [planning]
priority: 50
enabled: true
version: v1
content: Classify only. Do not execute.
tags: []
metadata: {}
""",
    )
    _write_module(
        prompts_root,
        "risk/low.yaml",
        """
id: low_risk
scope: risk
applies_to: [low]
priority: 20
enabled: true
version: v1
content: Prefer the least risky matching capability.
tags: []
metadata: {}
""",
    )
    _write_module(
        prompts_root,
        "user/resolver.yaml",
        """
id: resolver_target
scope: user
applies_to: [resolver]
priority: 10
enabled: true
version: v1
content: Return only JSON for capability resolution.
tags: []
metadata: {}
""",
    )

    llm = FakeResolverLLM(
        """
{
  "capability": "system_inspection.check_disk_usage",
  "arguments": {"path": "/home"},
  "confidence": 0.93
}
"""
    )

    result = resolve_intent_to_capability(
        user_input="check disk usage for /home",
        registry=_registry_with_disk_capability(),
        llm_client=llm,
        language="en",
        prompts_root=prompts_root,
    )

    assert result.capability_name == "system_inspection.check_disk_usage"
    assert result.arguments == {"path": "/home"}
    assert result.prompt_build is not None
    assert result.capability_candidates
    assert "[GLOBAL SAFETY]" in llm.calls[0][0]
    assert "[ROLE: PLANNER]" in llm.calls[0][0]
    assert "[CAPABILITY: system_inspection.check_disk_usage]" in llm.calls[0][0]


def test_resolver_fails_closed_when_prompt_build_fails(tmp_path: Path) -> None:
    prompts_root = tmp_path / "prompts"
    _write_module(
        prompts_root,
        "step/planner.yaml",
        """
id: planner_role
scope: step
applies_to: [planning]
priority: 50
enabled: true
version: v1
content: Classify only. Do not execute.
tags: []
metadata: {}
""",
    )

    result = resolve_intent_to_capability(
        user_input="check disk usage for /home",
        registry=_registry_with_disk_capability(),
        llm_client=FakeResolverLLM("{}"),
        language="en",
        prompts_root=prompts_root,
    )

    assert result.capability_name is None
    assert result.clarification_question is not None
    assert result.prompt_build is None
