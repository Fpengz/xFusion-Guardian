from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from xfusion.execution.allowlist import ExecutableRegistry

FallbackType = Literal[
    "template_execution",
    "restricted_command_execution",
    "agent_generated_python",
]


@dataclass(frozen=True)
class FallbackExecutionRequest:
    fallback_type: FallbackType
    justification: str
    policy_approved: bool
    argv: list[str] | None = None
    code: str | None = None
    sandbox: dict[str, Any] | None = None
    budget_reserved: bool = False
    verification: dict[str, Any] | None = None


@dataclass(frozen=True)
class FallbackExecutionResult:
    status: str
    reason: str
    audit: dict[str, Any]


@dataclass(frozen=True)
class SandboxPolicy:
    allowed_files: list[str]
    allow_network: bool
    allow_subprocess: bool
    allowed_imports: list[str]
    max_cpu_ms: int = 1000
    max_memory_bytes: int = 32_000_000
    max_wall_time_ms: int = 1000
    max_output_bytes: int = 8192

    def validate_code(self, code: str) -> str | None:
        if "__import__(" in code:
            return "sandbox_dynamic_import_forbidden"
        for line in code.splitlines():
            stripped = line.strip()
            if stripped.startswith("import "):
                modules = [part.strip().split(" ", 1)[0] for part in stripped[7:].split(",")]
                for module in modules:
                    reason = self._validate_import(module)
                    if reason:
                        return reason
            if stripped.startswith("from "):
                module = stripped[5:].split(" ", 1)[0]
                reason = self._validate_import(module)
                if reason:
                    return reason
        if not self.allow_subprocess and "subprocess" in code:
            return "sandbox_subprocess_forbidden"
        if not self.allow_network and any(
            token in code for token in ("socket", "urllib", "http.client")
        ):
            return "sandbox_network_forbidden"
        for quoted in ("'/", '"/'):
            if quoted in code:
                paths = _extract_absolute_paths(code)
                for path in paths:
                    if path not in self.allowed_files:
                        return "sandbox_file_scope_violation"
        return None

    def _validate_import(self, module: str) -> str | None:
        root_module = module.split(".", 1)[0]
        if root_module not in set(self.allowed_imports):
            return f"sandbox_import_forbidden:{root_module}"
        return None


class FallbackExecutor:
    """Constrained fallback execution gate.

    This class intentionally does not execute commands yet. It enforces the
    safety contract that fallback requests must be approved and, for generated
    Python, explicitly sandbox-enabled before a future runtime can run them.
    """

    def __init__(
        self,
        *,
        allow_agent_generated_python: bool = False,
        executables: ExecutableRegistry | None = None,
    ) -> None:
        self.allow_agent_generated_python = allow_agent_generated_python
        self.executables = executables

    def execute(self, request: FallbackExecutionRequest) -> FallbackExecutionResult:
        if not request.justification.strip():
            return self._denied("missing_justification")
        if not request.policy_approved:
            return self._denied("policy_approval_required")
        if not request.budget_reserved:
            return self._denied("budget_reservation_required")
        if not request.verification or not request.verification.get("type"):
            return self._denied("verification_required")
        if request.fallback_type == "agent_generated_python":
            if not self.allow_agent_generated_python:
                return self._denied("agent_generated_python_disabled")
            sandbox = request.sandbox or {}
            if sandbox.get("allow_network") or sandbox.get("allow_subprocess"):
                return self._denied("sandbox_network_or_subprocess_forbidden")
            if "allow_files" not in sandbox:
                return self._denied("sandbox_file_scope_required")
            return self._denied("sandbox_runtime_not_configured")
        if request.fallback_type == "restricted_command_execution":
            if not request.argv:
                return self._denied("argv_required")
            if any(token in {"|", ";", "&&", "||", ">", "<"} for token in request.argv):
                return self._denied("shell_semantics_forbidden")
            if self.executables is not None and request.argv[0] not in set(
                self.executables.all().values()
            ):
                return self._denied("fallback_executable_not_allowlisted")
            return self._denied("restricted_command_runtime_not_configured")
        if request.fallback_type == "template_execution":
            return self._denied("template_runtime_not_configured")
        return self._denied("unsupported_fallback_type")

    def _denied(self, reason: str) -> FallbackExecutionResult:
        return FallbackExecutionResult(
            status="denied",
            reason=reason,
            audit={"execution_surface": "fallback", "status": "denied", "reason": reason},
        )


def _extract_absolute_paths(code: str) -> list[str]:
    paths: list[str] = []
    for quote in ("'", '"'):
        parts = code.split(quote)
        for index, part in enumerate(parts):
            if index % 2 == 1 and part.startswith("/"):
                paths.append(part)
    return paths
