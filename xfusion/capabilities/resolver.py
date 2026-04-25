"""LLM-driven capability resolver for XFusion v0.2.4.2.

This module implements tool-style capability loading where the LLM acts as the router,
selecting appropriate capabilities based on natural language input and capability schemas.
"""

from __future__ import annotations

import json
from typing import Any

from xfusion.capabilities.registry import CapabilityRegistry
from xfusion.domain.models.capability import CapabilityDefinition


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


def resolve_intent_to_capability(
    user_input: str,
    registry: CapabilityRegistry,
    llm_client: Any | None = None,
    language: str = "en",
) -> tuple[str | None, dict[str, Any] | None, str | None]:
    """Use LLM to resolve user intent to a capability and extract parameters.

    Returns:
        Tuple of (capability_name, extracted_args, clarification_question)
        - If successful: (capability_name, args_dict, None)
        - If needs clarification: (None, {}, clarification_string)
        - If no capability matches: (None, {}, None)
    """
    if not llm_client:
        # Fallback to simple keyword matching if no LLM available
        return _fallback_keyword_matching(user_input)

    tool_schemas = build_tool_schemas(registry)

    system_prompt = """You are an intent classifier for XFusion, a secure system operations agent.
Your task is to match user requests to available capabilities (tools).

Rules:
1. Only select a capability if the user's intent clearly matches its purpose
2. Extract parameters from the user input that match the capability's schema
3. If the request is ambiguous or missing required parameters, ask for clarification
4. Never invent capabilities that don't exist in the provided list
5. Prefer read-only capabilities when the intent is unclear
6. Consider risk tiers - higher risk requires clearer intent

Respond in JSON format with exactly one of these structures:
{
  "capability": "capability.name",
  "arguments": {"param1": "value1", "param2": "value2"},
  "confidence": 0.95
}

OR if clarification is needed:
{
  "clarification": "What specific path should I check?",
  "missing_parameters": ["path"]
}

OR if no capability matches:
{
  "no_match": true,
  "reason": "This request is outside my allowed operations"
}"""

    user_prompt = f"""Available capabilities:
{json.dumps(tool_schemas, indent=2)}

User request: {user_input}

Language: {language}

Select the most appropriate capability and extract arguments."""

    try:
        response = llm_client.complete(system_prompt, user_prompt, timeout=15.0)

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
            return None, {}, None

        if "clarification" in result:
            return None, {}, result["clarification"]

        if "capability" in result:
            capability_name = result["capability"]
            # Validate capability exists
            if not registry.has(capability_name):
                return None, {}, f"Unknown capability: {capability_name}"

            arguments = result.get("arguments", {})
            return capability_name, arguments, None

        # Fallback if response format is unexpected
        return None, {}, None

    except (json.JSONDecodeError, Exception):
        # On LLM failure, fall back to keyword matching
        return _fallback_keyword_matching(user_input)


def _fallback_keyword_matching(
    user_input: str,
) -> tuple[str | None, dict[str, Any] | None, str | None]:
    """Simple keyword-based fallback when LLM is unavailable.

    This maintains backward compatibility during transition period.
    """
    user_input_lower = user_input.lower()

    # Disk operations
    if "disk" in user_input_lower or "磁盘" in user_input_lower or "空间" in user_input_lower:
        if "clean" in user_input_lower or "full" in user_input_lower or "清" in user_input_lower:
            # Multi-step disk cleanup handled in plan_node
            return None, {}, None
        return "disk.check_usage", {"path": "/"}, None

    # Memory operations
    elif "ram" in user_input_lower or "memory" in user_input_lower:
        return "system.check_ram", {}, None

    # Process operations
    elif "list processes" in user_input_lower or (
        "processes" in user_input_lower and "port" not in user_input_lower
    ):
        return "process.list", {"limit": 20}, None
    elif "port" in user_input_lower:
        import re

        port_match = re.search(r"port\s+(\d+)", user_input_lower)
        port = int(port_match.group(1)) if port_match else 8080
        if any(word in user_input_lower for word in ("stop", "kill")):
            # Multi-step planning handled in plan_node
            return None, {}, None
        return "process.find_by_port", {"port": port}, None

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
        return "user.create", {"username": username}, None
    elif "delete user" in user_input_lower or "remove user" in user_input_lower:
        import re

        # Handle both "Delete user olduser" and "delete olduser" patterns
        match = re.search(r"(?:delete|remove)\s+user\s+(\S+)", user_input, re.IGNORECASE)
        username = match.group(1) if match else "demoagent"
        return "user.delete", {"username": username}, None

    # File operations
    elif "preview metadata" in user_input_lower:
        path = user_input.split("for", 1)[1].strip(" .") or "."
        return "file.preview_metadata", {"path": path}, None
    elif "search for" in user_input_lower or "find files named" in user_input_lower:
        import re

        query_match = re.search(r'"([^"]+)"', user_input)
        query = query_match.group(1) if query_match else user_input.split()[-1]
        return "file.search", {"query": query, "path": ".", "limit": 20}, None

    # System info
    elif "environment" in user_input_lower or "os" in user_input_lower:
        return "system.detect_os", {}, None

    # Forbidden operations
    elif "chmod" in user_input_lower and "/usr" in user_input_lower:
        return "plan.explain_action", {"path": "/usr", "action": "chmod"}, None

    return None, {}, None
