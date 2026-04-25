"""LLM-driven capability resolver for XFusion v0.2.4.4.

This module implements tool-style capability loading where the LLM acts as the router,
selecting appropriate capabilities based on natural language input and capability schemas.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, cast

from xfusion.capabilities.registry import CapabilityRegistry
from xfusion.capabilities.retrieval import CapabilityCandidate, CapabilityRetriever
from xfusion.domain.models.capability import CapabilityDefinition
from xfusion.prompts import PromptContext, build_prompt, capability_prompt_module
from xfusion.prompts.prompt_composer import PromptBuildResult
from xfusion.prompts.prompt_registry import PromptRegistry, PromptRegistryError
from xfusion.prompts.prompt_selector import PromptRiskLevel


def capability_to_tool_schema(capability: CapabilityDefinition) -> dict[str, Any]:
    """Convert a CapabilityDefinition to an OpenAI-compatible tool schema.

    This enables the LLM to understand available capabilities and select the appropriate one.
    """
    return {
        "type": "function",
        "function": {
            "name": capability.name,
            "description": f"{capability.verb} {capability.object}. "
            f"Risk Tier: {capability.risk_tier.value}. "
            f"Approval: {capability.approval_mode.value}. "
            f"{'Read-only operation.' if capability.is_read_only else 'Modifies system state.'}",
            "parameters": capability.input_schema,
        },
    }


def build_tool_schemas(registry: CapabilityRegistry) -> list[dict[str, Any]]:
    """Build OpenAI-compatible tool schemas from all registered capabilities."""
    return [capability_to_tool_schema(cap) for cap in registry.all()]


class CapabilityResolutionResult:
    """Structured capability resolution output with explainability."""

    def __init__(
        self,
        *,
        capability_name: str | None = None,
        arguments: dict[str, Any] | None = None,
        clarification_question: str | None = None,
        no_match_reason: str | None = None,
        prompt_build: PromptBuildResult | None = None,
        capability_candidates: list[CapabilityCandidate] | None = None,
    ) -> None:
        self.capability_name = capability_name
        self.arguments = arguments or {}
        self.clarification_question = clarification_question
        self.no_match_reason = no_match_reason
        self.prompt_build = prompt_build
        self.capability_candidates = capability_candidates or []


def resolve_intent_to_capability(
    user_input: str,
    registry: CapabilityRegistry,
    llm_client: Any | None = None,
    language: str = "en",
    prompts_root: str | Path | None = None,
) -> CapabilityResolutionResult:
    """Use LLM to resolve user intent to a capability and extract parameters.

    Returns:
        Tuple of (capability_name, extracted_args, clarification_question)
        - If successful: (capability_name, args_dict, None)
        - If needs clarification: (None, {}, clarification_string)
        - If no capability matches: (None, {}, None)
    """
    candidates = CapabilityRetriever(registry).retrieve(user_input, top_k=5).candidates
    if not llm_client:
        # Fallback to simple keyword matching if no LLM available
        fallback = _fallback_keyword_matching(user_input)
        fallback.capability_candidates = candidates
        return fallback

    shortlisted_capabilities = [
        registry.require(candidate.name) for candidate in candidates if registry.has(candidate.name)
    ]
    active_capability = shortlisted_capabilities[0] if shortlisted_capabilities else None
    prompt_registry = PromptRegistry(prompts_root) if prompts_root else None
    extra_rejected: list[dict[str, object]] = []
    extra_why_selected = [candidate.why_selected for candidate in candidates]
    for candidate in candidates:
        for alternative in candidate.rejected_alternatives:
            extra_rejected.append(
                {
                    "module_id": str(alternative["name"]),
                    "version": "capability_candidate",
                    "scope": "capability",
                    "reason": str(alternative["reason"]),
                }
            )

    try:
        prompt_build = build_prompt(
            ctx=PromptContext(
                step_type="planning",
                capability=active_capability.name if active_capability else None,
                risk_level=_prompt_risk_from_candidates(shortlisted_capabilities),
                project_context={"prompt_targets": ["resolver"]},
            ),
            registry=prompt_registry,
            capability_modules=(
                [
                    capability_prompt_module(
                        active_capability.name,
                        instructions=active_capability.prompt.instructions,
                        constraints=active_capability.prompt.constraints,
                    )
                ]
                if active_capability
                else None
            ),
            extra_why_selected=extra_why_selected,
            extra_rejected=extra_rejected,
        )
    except (PromptRegistryError, ValueError):
        return CapabilityResolutionResult(
            clarification_question=(
                "I couldn't safely construct the resolver prompt for this request."
            ),
            capability_candidates=candidates,
        )
    tool_schemas = [
        capability_to_tool_schema(capability) for capability in shortlisted_capabilities
    ]

    user_prompt = f"""Available capabilities:
{json.dumps(tool_schemas, indent=2)}

Capability candidate explainability:
{json.dumps([candidate.model_dump() for candidate in candidates], indent=2)}

User request: {user_input}

Language: {language}

Select the most appropriate capability and extract arguments."""

    try:
        response = llm_client.complete(prompt_build.system_prompt, user_prompt, timeout=15.0)

        # Parse JSON response
        response_text = response.strip()
        if response_text.startswith("```json"):
            response_text = response_text[7:]
        if response_text.startswith("```"):
            response_text = response_text[3:]
        if response_text.endswith("```"):
            response_text = response_text[:-3]
        response_text = response_text.strip()

        result = json.loads(response_text)

        if "no_match" in result and result["no_match"]:
            return CapabilityResolutionResult(
                no_match_reason=str(result.get("reason", "")) or "no_capability_match",
                prompt_build=prompt_build,
                capability_candidates=candidates,
            )

        if "clarification" in result:
            return CapabilityResolutionResult(
                clarification_question=str(result["clarification"]),
                prompt_build=prompt_build,
                capability_candidates=candidates,
            )

        if "capability" in result:
            capability_name = result["capability"]
            # Validate capability exists
            if not registry.has(capability_name):
                return CapabilityResolutionResult(
                    clarification_question=f"Unknown capability: {capability_name}",
                    prompt_build=prompt_build,
                    capability_candidates=candidates,
                )

            arguments = result.get("arguments", {})
            return CapabilityResolutionResult(
                capability_name=capability_name,
                arguments=arguments,
                prompt_build=prompt_build,
                capability_candidates=candidates,
            )

        # Fallback if response format is unexpected
        return CapabilityResolutionResult(
            no_match_reason="unexpected_resolver_output",
            prompt_build=prompt_build,
            capability_candidates=candidates,
        )

    except (json.JSONDecodeError, Exception):
        # On LLM failure, fall back to keyword matching
        fallback = _fallback_keyword_matching(user_input)
        fallback.prompt_build = prompt_build
        fallback.capability_candidates = candidates
        return fallback


def _fallback_keyword_matching(
    user_input: str,
) -> CapabilityResolutionResult:
    """Simple keyword-based fallback when LLM is unavailable.

    This maintains backward compatibility during transition period.
    """
    user_input_lower = user_input.lower()

    # Disk operations
    if "disk" in user_input_lower or "磁盘" in user_input_lower or "空间" in user_input_lower:
        if "clean" in user_input_lower or "full" in user_input_lower or "清" in user_input_lower:
            # Multi-step disk cleanup handled in plan_node
            return CapabilityResolutionResult()
        return CapabilityResolutionResult(
            capability_name="disk.check_usage",
            arguments={"path": "/"},
        )

    # Memory operations
    elif "ram" in user_input_lower or "memory" in user_input_lower:
        return CapabilityResolutionResult(capability_name="system.check_ram", arguments={})

    # Process operations
    elif "list processes" in user_input_lower or (
        "processes" in user_input_lower and "port" not in user_input_lower
    ):
        return CapabilityResolutionResult(
            capability_name="process.list",
            arguments={"limit": 20},
        )
    elif "port" in user_input_lower:
        import re

        port_match = re.search(r"port\s+(\d+)", user_input_lower)
        port = int(port_match.group(1)) if port_match else 8080
        if any(word in user_input_lower for word in ("stop", "kill")):
            # Multi-step planning handled in plan_node
            return CapabilityResolutionResult()
        return CapabilityResolutionResult(
            capability_name="process.find_by_port",
            arguments={"port": port},
        )

    # User operations
    elif (
        "create user" in user_input_lower
        or "create a new user" in user_input_lower
        or "create new user" in user_input_lower
    ):
        import re

        # Handle "Create user alice", "Create a new user alice", "Create new user alice"
        match = re.search(
            r"(?:create\s+(?:a\s+)?(?:new\s+)?user)\s+(\S+)", user_input, re.IGNORECASE
        )
        username = match.group(1) if match else "demoagent"
        return CapabilityResolutionResult(
            capability_name="user.create",
            arguments={"username": username},
        )
    elif "delete user" in user_input_lower or "remove user" in user_input_lower:
        import re

        # Handle both "Delete user olduser" and "delete olduser" patterns
        match = re.search(r"(?:delete|remove)\s+user\s+(\S+)", user_input, re.IGNORECASE)
        username = match.group(1) if match else "demoagent"
        return CapabilityResolutionResult(
            capability_name="user.delete",
            arguments={"username": username},
        )

    # File operations
    elif "preview metadata" in user_input_lower:
        path = user_input.split("for", 1)[1].strip(" .") or "."
        return CapabilityResolutionResult(
            capability_name="file.preview_metadata",
            arguments={"path": path},
        )
    elif "search for" in user_input_lower or "find files named" in user_input_lower:
        import re

        query_match = re.search(r'"([^"]+)"', user_input)
        query = query_match.group(1) if query_match else user_input.split()[-1]
        return CapabilityResolutionResult(
            capability_name="file.search",
            arguments={"query": query, "path": ".", "limit": 20},
        )

    # System info
    elif "environment" in user_input_lower or "os" in user_input_lower:
        return CapabilityResolutionResult(capability_name="system.detect_os", arguments={})

    # Forbidden operations
    elif "chmod" in user_input_lower and "/usr" in user_input_lower:
        return CapabilityResolutionResult(
            capability_name="plan.explain_action",
            arguments={"path": "/usr", "action": "chmod"},
        )

    return CapabilityResolutionResult()


def _prompt_risk_from_candidates(
    candidates: list[CapabilityDefinition],
) -> PromptRiskLevel:
    priority = {"tier_0": "low", "tier_1": "medium", "tier_2": "high", "tier_3": "high"}
    selected = "low"
    for capability in candidates:
        mapped = priority.get(str(capability.risk_tier), "high")
        if mapped == "high":
            return "high"
        if mapped == "medium":
            selected = "medium"
    return cast(PromptRiskLevel, selected)
