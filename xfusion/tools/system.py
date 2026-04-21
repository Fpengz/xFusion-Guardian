from __future__ import annotations

import os
import shutil
import subprocess

from xfusion.domain.models.environment import EnvironmentState
from xfusion.execution.command_runner import CommandRunner
from xfusion.tools.base import ToolOutput


class SystemTools:
    """Tools for environment detection and system status."""

    def __init__(self, runner: CommandRunner) -> None:
        self.runner = runner

    def detect_os(self) -> ToolOutput:
        """Detect distro, version, and other system facts."""
        state = EnvironmentState()

        # Detect distro
        res = self.runner.run(["cat", "/etc/os-release"])
        if res.exit_code == 0:
            for line in res.stdout.splitlines():
                if line.startswith("ID="):
                    state.distro_family = line.split("=")[1].strip('"')
                if line.startswith("VERSION_ID="):
                    state.distro_version = line.split("=")[1].strip('"')

        # Detect user
        state.current_user = os.environ.get("USER") or os.environ.get("LOGNAME") or "unknown"

        # Sudo availability
        res = self.runner.run(["sudo", "-n", "true"])
        state.sudo_available = res.exit_code == 0

        # Systemd availability
        state.systemd_available = os.path.exists("/run/systemd/system")

        # Package manager
        if shutil.which("apt"):
            state.package_manager = "apt"
        elif shutil.which("yum"):
            state.package_manager = "yum"
        elif shutil.which("dnf"):
            state.package_manager = "dnf"

        # Disk pressure (simplified for v0.1)
        res = self.runner.run(["df", "/", "--output=pcent"])
        if res.exit_code == 0:
            try:
                pcent = int(res.stdout.splitlines()[1].strip().rstrip("%"))
                state.disk_pressure = "high" if pcent > 90 else "normal"
            except (ValueError, IndexError):
                state.disk_pressure = "unknown"

        return ToolOutput(
            summary=f"Detected {state.distro_family} {state.distro_version} environment.",
            data=state.model_dump(),
        )

    def check_ram(self) -> ToolOutput:
        """Report current RAM usage."""
        res = self.runner.run(["free", "-h"])
        if res.exit_code == 0:
            return ToolOutput(summary=f"RAM usage:\n{res.stdout}", data={"stdout": res.stdout})
        return ToolOutput(
            summary=f"Failed to check RAM usage: {res.stderr}", data={"error": res.stderr}
        )

    def current_user(self) -> ToolOutput:
        """Report the current effective user."""
        res = self.runner.run(["id", "-un"])
        user = res.stdout.strip() if res.exit_code == 0 else os.environ.get("USER", "unknown")
        return ToolOutput(summary=f"Current user: {user}", data={"user": user})

    def check_sudo(self) -> ToolOutput:
        """Report whether passwordless sudo is currently available."""
        res = self.runner.run(["sudo", "-n", "true"])
        available = res.exit_code == 0
        return ToolOutput(
            summary="Passwordless sudo is available."
            if available
            else "Passwordless sudo is unavailable.",
            data={"sudo_available": available},
        )

    def service_status(self, service: str) -> ToolOutput:
        """Report service status using systemctl when available."""
        res = self.runner.run(["systemctl", "is-active", service])
        status = res.stdout.strip() if res.stdout.strip() else "unknown"
        if res.exit_code in {0, 3}:
            return ToolOutput(
                summary=f"Service {service} status: {status}",
                data={"service": service, "status": status},
            )
        stderr = res.stderr.decode() if isinstance(res.stderr, bytes) else res.stderr
        if "System has not been booted with systemd" in stderr:
            return ToolOutput(
                summary="systemd is unavailable in this environment.",
                data={"service": service, "status": "unavailable"},
            )
        raise subprocess.SubprocessError(stderr or f"Could not inspect service {service}.")
