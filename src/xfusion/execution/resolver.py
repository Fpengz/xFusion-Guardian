"""Hybrid execution resolver for v0.2.4.3 three-tier model."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from xfusion.capabilities.registry import CapabilityRegistry
from xfusion.capabilities.templates import TemplateEngine
from xfusion.domain.models.capability import CapabilityDefinition
from xfusion.execution.restricted_shell import (
    RestrictedShellExecutor,
    ShellRiskLevel,
)
from xfusion.policy.categories import PolicyCategory
from xfusion.policy.envelope import normalize_command_fingerprint


class ExecutionTier(StrEnum):
    """Three-tier execution model."""

    TIER_1_CAPABILITY = "tier_1_capability"
    TIER_2_TEMPLATE = "tier_2_template"
    TIER_3_RESTRICTED_SHELL = "tier_3_restricted_shell"


@dataclass(frozen=True)
class ResolutionResult:
    """Result of capability resolution across all tiers."""

    tier: ExecutionTier
    success: bool
    capability_name: str | None = None
    template_name: str | None = None
    command: str | None = None
    risk_level: PolicyCategory | None = None
    requires_confirmation: bool = False
    requires_admin: bool = False
    error: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ExecutionOutcome:
    """Final outcome after execution."""

    tier: ExecutionTier
    success: bool
    output: Any
    risk_category: PolicyCategory
    confirmation_obtained: bool = False
    audit_data: dict[str, Any] = field(default_factory=dict)


class HybridExecutionResolver:
    """Resolver implementing the three-tier hybrid execution model.

    Flow:
    1. Try Tier 1: Registered capabilities (first-class, typed operations)
    2. Try Tier 2: Structured command templates (predefined structures)
    3. Fallback to Tier 3: Restricted dynamic shell (last resort)

    All tiers pass through shared policy engine for confirmation/execution gating.
    """

    def __init__(
        self,
        capability_registry: CapabilityRegistry,
        template_engine: TemplateEngine,
        shell_executor: RestrictedShellExecutor | None = None,
    ) -> None:
        self.capability_registry = capability_registry
        self.template_engine = template_engine
        self.shell_executor = shell_executor or RestrictedShellExecutor()

    def resolve(
        self,
        intent: str,
        llm_selected_tool: dict[str, Any] | None = None,
        template_name: str | None = None,
        template_params: dict[str, Any] | None = None,
        shell_command: str | None = None,
    ) -> ResolutionResult:
        """Resolve intent to appropriate execution tier.

        Args:
            intent: Natural language description of desired action
            llm_selected_tool: Tool selection from LLM (name + arguments)
            template_name: Explicit template name for Tier 2
            template_params: Parameters for template rendering
            shell_command: Raw shell command for Tier 3 fallback

        Returns:
            ResolutionResult with tier selection and metadata
        """
        del intent  # Agent-supplied candidates carry semantic applicability.

        agent_requested_surface = llm_selected_tool.get("type") if llm_selected_tool else None
        applicable_capabilities = (
            llm_selected_tool.get("applicable_capabilities", []) if llm_selected_tool else []
        )
        for candidate in applicable_capabilities:
            if not isinstance(candidate, dict):
                continue
            name = candidate.get("name")
            if isinstance(name, str) and self.capability_registry.has(name):
                capability = self.capability_registry.require(name)
                tool_args = candidate.get("arguments", {})
                risk_category = self._capability_to_policy_category(capability)
                return ResolutionResult(
                    tier=ExecutionTier.TIER_1_CAPABILITY,
                    success=True,
                    capability_name=name,
                    risk_level=risk_category,
                    requires_confirmation=self._requires_confirmation(risk_category),
                    requires_admin=self._requires_admin(risk_category),
                    metadata={
                        "capability": capability.name,
                        "arguments": tool_args,
                        "risk_tier": capability.risk_tier.value,
                        "approval_mode": capability.approval_mode.value,
                        "surface_order_enforced": True,
                        "agent_requested_surface": agent_requested_surface,
                    },
                )

        # Tier 1: Try registered capabilities first
        if llm_selected_tool:
            tool_name = llm_selected_tool.get("name")
            tool_args = llm_selected_tool.get("arguments", {})

            if tool_name and self.capability_registry.has(tool_name):
                capability = self.capability_registry.require(tool_name)
                risk_category = self._capability_to_policy_category(capability)

                return ResolutionResult(
                    tier=ExecutionTier.TIER_1_CAPABILITY,
                    success=True,
                    capability_name=tool_name,
                    risk_level=risk_category,
                    requires_confirmation=self._requires_confirmation(risk_category),
                    requires_admin=self._requires_admin(risk_category),
                    metadata={
                        "capability": capability.name,
                        "arguments": tool_args,
                        "risk_tier": capability.risk_tier.value,
                        "approval_mode": capability.approval_mode.value,
                    },
                )

        applicable_templates = (
            llm_selected_tool.get("applicable_templates", []) if llm_selected_tool else []
        )
        for candidate in applicable_templates:
            if not isinstance(candidate, dict):
                continue
            name = candidate.get("name")
            params = candidate.get("arguments", {})
            if not isinstance(name, str) or not isinstance(params, dict):
                continue
            validation = self.template_engine.validate_parameters(name, params)
            if validation.valid and validation.resolved_command:
                template = self.template_engine.get_template(name)
                if template:
                    return ResolutionResult(
                        tier=ExecutionTier.TIER_2_TEMPLATE,
                        success=True,
                        template_name=name,
                        command=validation.resolved_command,
                        risk_level=template.category,
                        requires_confirmation=self._requires_confirmation(template.category),
                        requires_admin=self._requires_admin(template.category),
                        metadata={
                            "template": name,
                            "parameters": params,
                            "rendered_command": validation.resolved_command,
                            "surface_order_enforced": True,
                            "agent_requested_surface": agent_requested_surface,
                        },
                    )

        # Tier 2: Try structured templates
        if template_name or (llm_selected_tool and llm_selected_tool.get("type") == "template"):
            name = template_name or (llm_selected_tool.get("name") if llm_selected_tool else None)
            params = template_params or (
                llm_selected_tool.get("arguments", {}) if llm_selected_tool else {}
            )

            if name:
                validation = self.template_engine.validate_parameters(name, params)
                if validation.valid and validation.resolved_command:
                    template = self.template_engine.get_template(name)
                    if template:
                        return ResolutionResult(
                            tier=ExecutionTier.TIER_2_TEMPLATE,
                            success=True,
                            template_name=name,
                            command=validation.resolved_command,
                            risk_level=template.category,
                            requires_confirmation=self._requires_confirmation(template.category),
                            requires_admin=self._requires_admin(template.category),
                            metadata={
                                "template": name,
                                "parameters": params,
                                "rendered_command": validation.resolved_command,
                            },
                        )

        # Tier 3: Restricted shell fallback
        if shell_command or (llm_selected_tool and llm_selected_tool.get("type") == "shell"):
            command = shell_command or (
                llm_selected_tool.get("command") if llm_selected_tool else None
            )

            if command:
                fallback_reason = (
                    llm_selected_tool.get("fallback_reason") if llm_selected_tool else None
                )
                if not isinstance(fallback_reason, dict) or not fallback_reason:
                    return ResolutionResult(
                        tier=ExecutionTier.TIER_3_RESTRICTED_SHELL,
                        success=False,
                        command=command,
                        error=("Restricted shell fallback requires a structured fallback reason"),
                    )
                risk_level = self.shell_executor.classify_command(command)
                policy_category = self.shell_executor.to_policy_category(risk_level)
                command_argv = command.split()

                # Check if command is forbidden
                if risk_level == ShellRiskLevel.FORBIDDEN:
                    return ResolutionResult(
                        tier=ExecutionTier.TIER_3_RESTRICTED_SHELL,
                        success=False,
                        command=command,
                        risk_level=policy_category,
                        requires_confirmation=False,
                        requires_admin=False,
                        error="Command classified as forbidden - cannot execute",
                        metadata={"risk_level": risk_level.value},
                    )

                return ResolutionResult(
                    tier=ExecutionTier.TIER_3_RESTRICTED_SHELL,
                    success=True,
                    command=command,
                    risk_level=policy_category,
                    requires_confirmation=self._requires_confirmation(policy_category),
                    requires_admin=self._requires_admin(policy_category),
                    metadata={
                        "command": command,
                        "risk_level": risk_level.value,
                        "fallback_reason": fallback_reason,
                        "raw_command_fingerprint": normalize_command_fingerprint(command_argv),
                    },
                )

        # No tier matched
        return ResolutionResult(
            tier=ExecutionTier.TIER_3_RESTRICTED_SHELL,
            success=False,
            error="No matching capability, template, or valid shell command found",
        )

    def execute(
        self,
        resolution: ResolutionResult,
        confirmed: bool = False,
        admin_approved: bool = False,
    ) -> ExecutionOutcome:
        """Execute resolved command with confirmation gating.

        Args:
            resolution: Result from resolve()
            confirmed: User confirmation obtained
            admin_approved: Admin approval obtained (for privileged actions)

        Returns:
            ExecutionOutcome with results and audit data
        """
        # Check confirmation requirements
        if resolution.requires_confirmation and not confirmed:
            return ExecutionOutcome(
                tier=resolution.tier,
                success=False,
                output=None,
                risk_category=resolution.risk_level or PolicyCategory.READ_ONLY,
                confirmation_obtained=False,
                audit_data={"error": "Confirmation required but not obtained"},
            )

        if resolution.requires_admin and not admin_approved:
            return ExecutionOutcome(
                tier=resolution.tier,
                success=False,
                output=None,
                risk_category=resolution.risk_level or PolicyCategory.READ_ONLY,
                confirmation_obtained=confirmed,
                audit_data={"error": "Admin approval required but not obtained"},
            )

        # Execute based on tier
        if resolution.tier == ExecutionTier.TIER_1_CAPABILITY:
            # Tier 1 execution would happen via tool registry
            # This is a placeholder - actual execution happens in app layer
            return ExecutionOutcome(
                tier=resolution.tier,
                success=True,
                output={
                    "status": "executed_via_capability",
                    "capability": resolution.capability_name,
                },
                risk_category=resolution.risk_level or PolicyCategory.READ_ONLY,
                confirmation_obtained=confirmed,
                audit_data=resolution.metadata,
            )

        elif resolution.tier == ExecutionTier.TIER_2_TEMPLATE:
            # Tier 2: Execute rendered command via restricted shell
            if not resolution.command:
                return ExecutionOutcome(
                    tier=resolution.tier,
                    success=False,
                    output=None,
                    risk_category=resolution.risk_level or PolicyCategory.READ_ONLY,
                    confirmation_obtained=confirmed,
                    audit_data={"error": "No rendered command available"},
                )

            result = self.shell_executor.execute(resolution.command)
            return ExecutionOutcome(
                tier=resolution.tier,
                success=result.success,
                output={
                    "stdout": result.stdout,
                    "stderr": result.stderr,
                    "exit_code": result.exit_code,
                },
                risk_category=resolution.risk_level or PolicyCategory.READ_ONLY,
                confirmation_obtained=confirmed,
                audit_data={
                    **resolution.metadata,
                    "execution_time_sec": result.execution_time_sec,
                    "timeout_occurred": result.timeout_occurred,
                },
            )

        elif resolution.tier == ExecutionTier.TIER_3_RESTRICTED_SHELL:
            # Tier 3: Execute via restricted shell
            if not resolution.command:
                return ExecutionOutcome(
                    tier=resolution.tier,
                    success=False,
                    output=None,
                    risk_category=resolution.risk_level or PolicyCategory.READ_ONLY,
                    confirmation_obtained=confirmed,
                    audit_data={"error": "No command available for execution"},
                )

            result = self.shell_executor.execute(resolution.command)
            return ExecutionOutcome(
                tier=resolution.tier,
                success=result.success,
                output={
                    "stdout": result.stdout,
                    "stderr": result.stderr,
                    "exit_code": result.exit_code,
                },
                risk_category=resolution.risk_level or PolicyCategory.READ_ONLY,
                confirmation_obtained=confirmed,
                audit_data={
                    **resolution.metadata,
                    "execution_time_sec": result.execution_time_sec,
                    "timeout_occurred": result.timeout_occurred,
                    "safety_violation": result.safety_violation,
                },
            )

        # Unknown tier
        return ExecutionOutcome(
            tier=resolution.tier,
            success=False,
            output=None,
            risk_category=PolicyCategory.READ_ONLY,
            confirmation_obtained=False,
            audit_data={"error": f"Unknown execution tier: {resolution.tier}"},
        )

    def _capability_to_policy_category(self, capability: CapabilityDefinition) -> PolicyCategory:
        """Map capability risk tier and approval mode to policy category."""
        from xfusion.domain.enums import ApprovalMode, RiskTier

        # Forbidden capabilities
        if capability.approval_mode == ApprovalMode.DENY:
            return PolicyCategory.FORBIDDEN

        # Privileged: high risk tier + admin approval
        if (
            capability.risk_tier in (RiskTier.TIER_2, RiskTier.TIER_3)
            and capability.approval_mode == ApprovalMode.ADMIN
        ):
            return PolicyCategory.PRIVILEGED

        # Destructive: requires human approval and not read-only
        if capability.approval_mode == ApprovalMode.HUMAN and not capability.is_read_only:
            # Check if it's a destructive operation by name
            destructive_verbs = {"delete", "terminate", "destroy", "remove"}
            if any(verb in capability.verb.lower() for verb in destructive_verbs):
                return PolicyCategory.DESTRUCTIVE
            return PolicyCategory.WRITE_SAFE

        # Read-only operations
        if capability.is_read_only:
            return PolicyCategory.READ_ONLY

        # Default to write_safe
        return PolicyCategory.WRITE_SAFE

    def _requires_confirmation(self, category: PolicyCategory) -> bool:
        """Check if a policy category requires confirmation."""
        from xfusion.policy.categories import requires_confirmation

        return requires_confirmation(category)

    def _requires_admin(self, category: PolicyCategory) -> bool:
        """Check if a policy category requires admin permission."""
        from xfusion.policy.categories import requires_admin_permission

        return requires_admin_permission(category)

    def list_capabilities(self) -> list[dict[str, Any]]:
        """List all registered capabilities with metadata."""
        return [
            {
                "name": cap.name,
                "description": f"{cap.verb} {cap.object}",
                "risk_tier": cap.risk_tier.value,
                "approval_mode": cap.approval_mode.value,
                "is_read_only": cap.is_read_only,
                "tier": ExecutionTier.TIER_1_CAPABILITY.value,
            }
            for cap in self.capability_registry.all()
        ]

    def list_templates(self) -> list[dict[str, Any]]:
        """List all available templates with metadata."""
        return [
            {
                "name": t.name,
                "description": t.description,
                "category": t.category.value,
                "confirm_required": t.confirm_required,
                "tier": ExecutionTier.TIER_2_TEMPLATE.value,
            }
            for t in self.template_engine.list_templates()
        ]
