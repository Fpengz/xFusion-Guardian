"""Restricted shell fallback for Tier 3 execution with safety constraints."""

from __future__ import annotations

import re
import subprocess
import time
from dataclasses import dataclass, field
from enum import StrEnum

from xfusion.policy.categories import PolicyCategory


class ShellRiskLevel(StrEnum):
    """Risk classification for shell commands."""

    READ_ONLY = "read_only"
    WRITE_SAFE = "write_safe"
    DESTRUCTIVE = "destructive"
    PRIVILEGED = "privileged"
    FORBIDDEN = "forbidden"


@dataclass(frozen=True)
class ShellSafetyConstraints:
    """Safety constraints for restricted shell execution."""

    max_timeout_sec: float = 30.0
    max_output_bytes: int = 100_000
    allowed_working_directories: tuple[str, ...] = field(default_factory=lambda: (".", "/tmp"))
    forbid_sudo: bool = True
    forbid_shell_expansion: bool = True
    argv_based_only: bool = True
    network_restricted: bool = True


@dataclass(frozen=True)
class ShellExecutionResult:
    """Result of restricted shell execution."""

    success: bool
    stdout: str
    stderr: str
    exit_code: int
    risk_level: ShellRiskLevel
    execution_time_sec: float
    timeout_occurred: bool = False
    safety_violation: str | None = None


# Forbidden command patterns - never allowed
FORBIDDEN_PATTERNS: list[re.Pattern] = [
    re.compile(r"rm\s+-rf\s+[/~]"),  # Destructive deletion from root/home
    re.compile(r"rm\s+-rf\s+\*"),  # Wildcard deletion
    re.compile(r"chmod\s+.*\s+/etc/"),  # System file permission change
    re.compile(r"chown\s+.*\s+/etc/"),  # System file ownership change
    re.compile(r"passwd\s+"),  # Password modification
    re.compile(r"user(del|mod|add)\s+"),  # User management
    re.compile(r"group(del|mod|add)\s+"),  # Group management
    re.compile(r"iptables\s+"),  # Firewall configuration
    re.compile(r"crontab\s+"),  # Cron job management
    re.compile(r"visudo"),  # Sudoers editing
    re.compile(r"/etc/sudoers"),  # Direct sudoers access
    re.compile(r"mkfs"),  # Filesystem creation
    re.compile(r"dd\s+if="),  # Raw disk writing
    re.compile(r">\s*/dev/"),  # Device writing
    re.compile(r"\|\s*bash"),  # Pipe to bash
    re.compile(r"\|\s*sh\s*$"),  # Pipe to sh
    re.compile(r"eval\s+"),  # Eval execution
    re.compile(r"exec\s+"),  # Exec replacement
]

# Privileged patterns - require admin approval
PRIVILEGED_PATTERNS: list[re.Pattern] = [
    re.compile(r"sudo\s+"),  # Privilege escalation
    re.compile(r"\bsu\b\s+"),  # User switch
    re.compile(r"apt-get\s+(install|remove|upgrade)"),  # Package management
    re.compile(r"yum\s+(install|remove|update)"),  # Package management
    re.compile(r"dnf\s+(install|remove|update)"),  # Package management
    re.compile(r"systemctl\s+(enable|disable|mask|unmask)"),  # Service management
    re.compile(r"service\s+(start|stop|restart)"),  # Service control
    re.compile(r"mount\s+"),  # Mount operations
    re.compile(r"umount\s+"),  # Unmount operations
    re.compile(r"fdisk"),  # Disk partitioning
    re.compile(r"parted"),  # Partition editing
]

# Destructive patterns - require explicit confirmation
DESTRUCTIVE_PATTERNS: list[re.Pattern] = [
    re.compile(r"\brm\s+"),  # File deletion
    re.compile(r"rmdir\s+"),  # Directory deletion
    re.compile(r"mv\s+\S+\s+/\S+"),  # Move to system paths
    re.compile(r"cp\s+\S+\s+/\S+"),  # Copy to system paths (potential overwrite)
    re.compile(r"ln\s+\S+\s+/\S+"),  # Link creation in system paths
    re.compile(r"find\s+.*\s+-exec\s+"),  # Find with exec
    re.compile(r"xargs\s+"),  # Xargs execution
    re.compile(r"kill\s+"),  # Process termination
    re.compile(r"pkill\s+"),  # Process kill by name
    re.compile(r"killall\s+"),  # Kill all by name
]

# Write-safe patterns - usually require confirmation
WRITE_SAFE_PATTERNS: list[re.Pattern] = [
    re.compile(r"echo\s+.*\s+>>?\s+"),  # Output redirection
    re.compile(r"cat\s+.*\s+>>?\s+"),  # Content appending
    re.compile(r"touch\s+"),  # File creation
    re.compile(r"mkdir\s+"),  # Directory creation
    re.compile(r"cp\s+"),  # File copy
    re.compile(r"mv\s+"),  # File move
    re.compile(r"chmod\s+"),  # Permission change (non-system)
    re.compile(r"chown\s+"),  # Ownership change (non-system)
]

# Read-only patterns - generally safe
READ_ONLY_PATTERNS: list[re.Pattern] = [
    re.compile(r"\bls\s+"),  # Directory listing
    re.compile(r"\bcat\s+"),  # File content reading
    re.compile(r"\bgrep\s+"),  # Pattern searching
    re.compile(r"\bps\s+"),  # Process status
    re.compile(r"\bdf\s+"),  # Disk usage
    re.compile(r"\bfree\s+"),  # Memory usage
    re.compile(r"\btop\b"),  # Top processes
    re.compile(r"\bhead\s+"),  # First lines of file
    re.compile(r"\btail\s+"),  # Last lines of file
    re.compile(r"\bwc\s+"),  # Word count
    re.compile(r"\bfind\s+.*\s+-name\s+"),  # Find by name (no exec)
    re.compile(r"\bwhich\s+"),  # Locate command
    re.compile(r"\bwhereis\s+"),  # Find binary location
    re.compile(r"\bstat\s+"),  # File statistics
    re.compile(r"\bfile\s+"),  # File type detection
    re.compile(r"\bdu\s+"),  # Disk usage by directory
]


class RestrictedShellExecutor:
    """Executor for restricted shell commands with safety constraints."""

    def __init__(self, constraints: ShellSafetyConstraints | None = None) -> None:
        self.constraints = constraints or ShellSafetyConstraints()

    def classify_command(self, command: str) -> ShellRiskLevel:
        """Classify a command's risk level based on pattern matching."""
        # Check forbidden patterns first
        for pattern in FORBIDDEN_PATTERNS:
            if pattern.search(command):
                return ShellRiskLevel.FORBIDDEN

        # Check privileged patterns
        for pattern in PRIVILEGED_PATTERNS:
            if pattern.search(command):
                return ShellRiskLevel.PRIVILEGED

        # Check destructive patterns
        for pattern in DESTRUCTIVE_PATTERNS:
            if pattern.search(command):
                return ShellRiskLevel.DESTRUCTIVE

        # Check write-safe patterns
        for pattern in WRITE_SAFE_PATTERNS:
            if pattern.search(command):
                return ShellRiskLevel.WRITE_SAFE

        # Check read-only patterns
        for pattern in READ_ONLY_PATTERNS:
            if pattern.search(command):
                return ShellRiskLevel.READ_ONLY

        # Unknown patterns default to write_safe for safety
        return ShellRiskLevel.WRITE_SAFE

    def check_safety_violations(self, command: str, cwd: str | None = None) -> str | None:
        """Check for safety violations before execution."""
        # Check forbidden patterns
        for pattern in FORBIDDEN_PATTERNS:
            if pattern.search(command):
                return f"Forbidden command pattern detected: {pattern.pattern}"

        # Check working directory restrictions
        if cwd:
            allowed_dirs = self.constraints.allowed_working_directories
            if not any(cwd.startswith(d) for d in allowed_dirs):
                return f"Working directory '{cwd}' not in allowed list: {allowed_dirs}"

        # Check for shell expansion if forbidden
        if self.constraints.forbid_shell_expansion:
            expansion_patterns = ["$", "`", "$(", "${", "~"]
            for pattern in expansion_patterns:
                if pattern in command:
                    return f"Shell expansion detected and forbidden: {pattern}"

        # Check for sudo if forbidden
        if self.constraints.forbid_sudo and "sudo" in command:
            return "Sudo commands are forbidden"

        return None

    def execute(
        self,
        command: str,
        cwd: str | None = None,
        env: dict[str, str] | None = None,
    ) -> ShellExecutionResult:
        """Execute a command with safety constraints."""
        start_time = time.time()

        # Classify risk level
        risk_level = self.classify_command(command)

        # Check for forbidden commands
        if risk_level == ShellRiskLevel.FORBIDDEN:
            return ShellExecutionResult(
                success=False,
                stdout="",
                stderr="Command classified as forbidden",
                exit_code=-1,
                risk_level=risk_level,
                execution_time_sec=0.0,
                safety_violation="Command matched forbidden pattern",
            )

        # Check safety violations
        violation = self.check_safety_violations(command, cwd)
        if violation:
            return ShellExecutionResult(
                success=False,
                stdout="",
                stderr=violation,
                exit_code=-1,
                risk_level=risk_level,
                execution_time_sec=0.0,
                safety_violation=violation,
            )

        # Execute with constraints
        try:
            # Use argv-based execution if required
            if self.constraints.argv_based_only:
                # Split command into argv (simple split, no shell parsing)
                argv = command.split()
                if not argv:
                    return ShellExecutionResult(
                        success=False,
                        stdout="",
                        stderr="Empty command",
                        exit_code=-1,
                        risk_level=risk_level,
                        execution_time_sec=0.0,
                        safety_violation="Empty command",
                    )

                result = subprocess.run(
                    argv,
                    capture_output=True,
                    text=True,
                    timeout=self.constraints.max_timeout_sec,
                    cwd=cwd,
                    env=env,
                    shell=False,  # Never use shell=True
                )
            else:
                result = subprocess.run(
                    command,
                    capture_output=True,
                    text=True,
                    timeout=self.constraints.max_timeout_sec,
                    cwd=cwd,
                    env=env,
                    shell=True,
                )

            execution_time = time.time() - start_time

            # Truncate output if too large
            stdout = result.stdout[: self.constraints.max_output_bytes]
            stderr = result.stderr[: self.constraints.max_output_bytes]

            return ShellExecutionResult(
                success=result.returncode == 0,
                stdout=stdout,
                stderr=stderr,
                exit_code=result.returncode,
                risk_level=risk_level,
                execution_time_sec=execution_time,
                timeout_occurred=False,
            )

        except subprocess.TimeoutExpired:
            execution_time = time.time() - start_time
            return ShellExecutionResult(
                success=False,
                stdout="",
                stderr=f"Command timed out after {self.constraints.max_timeout_sec}s",
                exit_code=-1,
                risk_level=risk_level,
                execution_time_sec=execution_time,
                timeout_occurred=True,
            )

        except Exception as e:
            execution_time = time.time() - start_time
            return ShellExecutionResult(
                success=False,
                stdout="",
                stderr=str(e),
                exit_code=-1,
                risk_level=risk_level,
                execution_time_sec=execution_time,
                safety_violation=f"Execution error: {e}",
            )

    def to_policy_category(self, risk_level: ShellRiskLevel) -> PolicyCategory:
        """Convert shell risk level to policy category."""
        mapping = {
            ShellRiskLevel.READ_ONLY: PolicyCategory.READ_ONLY,
            ShellRiskLevel.WRITE_SAFE: PolicyCategory.WRITE_SAFE,
            ShellRiskLevel.DESTRUCTIVE: PolicyCategory.DESTRUCTIVE,
            ShellRiskLevel.PRIVILEGED: PolicyCategory.PRIVILEGED,
            ShellRiskLevel.FORBIDDEN: PolicyCategory.FORBIDDEN,
        }
        return mapping[risk_level]
