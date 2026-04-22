from __future__ import annotations

from xfusion.domain.enums import RiskLevel
from xfusion.domain.models.environment import EnvironmentState
from xfusion.domain.models.policy import PolicyDecision
from xfusion.policy.protected_paths import is_protected


def evaluate_policy(
    *,
    tool: str,
    parameters: dict[str, object],
    environment: EnvironmentState,
) -> PolicyDecision:
    """Return deterministic policy decision for one planned tool call."""

    # Read-only tools are generally low risk
    if (
        tool.startswith("system.detect")
        or tool.startswith("system.check")
        or tool == "system.current_user"
        or tool == "system.service_status"
        or tool.startswith("disk.check")
        or tool.startswith("disk.find")
        or tool.startswith("file.search")
        or tool.startswith("file.preview")
        or tool.startswith("process.list")
        or tool.startswith("process.find")
    ):
        return PolicyDecision(
            risk_level=RiskLevel.LOW,
            allowed=True,
            requires_confirmation=False,
            reason="Read-only operation is low risk.",
        )

    if tool == "plan.explain_action":
        path = str(parameters.get("path", "the requested path"))
        action = str(parameters.get("action", "action"))
        return PolicyDecision(
            risk_level=RiskLevel.FORBIDDEN,
            allowed=False,
            requires_confirmation=False,
            reason=(
                f"Recursive {action} permission changes on protected path '{path}' are forbidden."
            ),
        )

    # Protected path check for any tool that takes a path
    if "path" in parameters:
        path = str(parameters["path"])
        if is_protected(path, environment.protected_paths):
            return PolicyDecision(
                risk_level=RiskLevel.FORBIDDEN,
                allowed=False,
                requires_confirmation=False,
                reason=f"Path '{path}' is protected and cannot be modified.",
            )
    if "paths" in parameters and isinstance(parameters["paths"], list):
        for raw_path in parameters["paths"]:
            path = str(raw_path)
            if is_protected(path, environment.protected_paths):
                return PolicyDecision(
                    risk_level=RiskLevel.FORBIDDEN,
                    allowed=False,
                    requires_confirmation=False,
                    reason=f"Path '{path}' is protected and cannot be modified.",
                )

    # Process kill is medium risk
    if tool == "process.kill":
        return PolicyDecision(
            risk_level=RiskLevel.MEDIUM,
            allowed=True,
            requires_confirmation=True,
            reason="Stopping a process can affect system services and requires confirmation.",
        )

    # User creation/deletion is medium risk
    if tool in {"user.create", "user.delete"}:
        return PolicyDecision(
            risk_level=RiskLevel.MEDIUM,
            allowed=True,
            requires_confirmation=True,
            reason=f"Modifying system users ({tool}) requires confirmation.",
        )

    # Cleanup is medium risk
    if tool == "cleanup.safe_disk_cleanup":
        if parameters.get("execute") is not True:
            return PolicyDecision(
                risk_level=RiskLevel.LOW,
                allowed=True,
                requires_confirmation=False,
                reason="Cleanup preview is read-only and bounded to approved candidates.",
            )
        return PolicyDecision(
            risk_level=RiskLevel.MEDIUM,
            allowed=True,
            requires_confirmation=True,
            reason="File cleanup deletes approved candidates and requires confirmation.",
        )

    # Default to forbidden for unknown mutating tools
    return PolicyDecision(
        risk_level=RiskLevel.FORBIDDEN,
        allowed=False,
        requires_confirmation=False,
        reason=f"Unknown or unauthorized tool '{tool}'.",
    )
