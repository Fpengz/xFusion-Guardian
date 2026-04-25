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
        else:
            # Cross-platform fallback for non-Linux hosts (for local development UX).
            uname_sys = self.runner.run(["uname", "-s"])
            if uname_sys.exit_code == 0:
                system_name = uname_sys.stdout.strip().lower()
                if system_name == "darwin":
                    state.distro_family = "darwin"
                elif system_name:
                    state.distro_family = system_name

            uname_rel = self.runner.run(["uname", "-r"])
            if uname_rel.exit_code == 0:
                state.distro_version = uname_rel.stdout.strip() or "unknown"
            if state.distro_family == "darwin":
                mac_ver = self.runner.run(["sw_vers", "-productVersion"])
                if mac_ver.exit_code == 0 and mac_ver.stdout.strip():
                    state.distro_version = mac_ver.stdout.strip()

        # Detect user
        state.current_user = os.environ.get("USER") or os.environ.get("LOGNAME") or "unknown"
        if state.current_user == "unknown":
            user_res = self.runner.run(["id", "-un"])
            if user_res.exit_code == 0 and user_res.stdout.strip():
                state.current_user = user_res.stdout.strip()

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
        elif shutil.which("brew"):
            state.package_manager = "brew"

        # Coarse environment signal used by policy and cleanup planning.
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
        return ToolOutput(summary=f"Current user: {user}", data={"username": user})

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

    def service_start(self, service: str) -> ToolOutput:
        """Start a service using systemctl."""
        res = self.runner.run(["sudo", "systemctl", "start", service])
        if res.exit_code == 0:
            return ToolOutput(
                summary=f"Started service {service}.",
                data={"service": service, "status": "started"},
            )
        return ToolOutput(
            summary=f"Failed to start service {service}: {res.stderr}",
            data={"error": res.stderr},
        )

    def service_stop(self, service: str) -> ToolOutput:
        """Stop a service using systemctl."""
        res = self.runner.run(["sudo", "systemctl", "stop", service])
        if res.exit_code == 0:
            return ToolOutput(
                summary=f"Stopped service {service}.",
                data={"service": service, "status": "stopped"},
            )
        return ToolOutput(
            summary=f"Failed to stop service {service}: {res.stderr}",
            data={"error": res.stderr},
        )

    def service_restart(self, service: str) -> ToolOutput:
        """Restart a service using systemctl."""
        res = self.runner.run(["sudo", "systemctl", "restart", service])
        if res.exit_code == 0:
            return ToolOutput(
                summary=f"Restarted service {service}.",
                data={"service": service, "status": "restarted"},
            )
        return ToolOutput(
            summary=f"Failed to restart service {service}: {res.stderr}",
            data={"error": res.stderr},
        )

    def service_reload(self, service: str) -> ToolOutput:
        """Reload a service using systemctl."""
        res = self.runner.run(["sudo", "systemctl", "reload", service])
        if res.exit_code == 0:
            return ToolOutput(
                summary=f"Reloaded service {service}.",
                data={"service": service, "status": "reloaded"},
            )
        return ToolOutput(
            summary=f"Failed to reload service {service}: {res.stderr}",
            data={"error": res.stderr},
        )

    def list_services(self) -> ToolOutput:
        """List active systemd services."""
        res = self.runner.run(["systemctl", "list-units", "--type=service", "--state=active"])
        if res.exit_code == 0:
            return ToolOutput(
                summary=f"Active services:\n{res.stdout}", data={"stdout": res.stdout}
            )
        return ToolOutput(
            summary=f"Failed to list services: {res.stderr}", data={"error": res.stderr}
        )

    def restart_failed_services(self) -> ToolOutput:
        """Find failed services and attempt to restart them."""
        # Find failed units
        res = self.runner.run(
            ["systemctl", "list-units", "--type=service", "--state=failed", "--no-legend"]
        )
        if res.exit_code != 0:
            return ToolOutput(
                summary="Failed to check for failed services.", data={"error": res.stderr}
            )

        failed_units = []
        for line in res.stdout.splitlines():
            parts = line.split()
            if parts:
                failed_units.append(parts[0])

        if not failed_units:
            return ToolOutput(summary="No failed services found.", data={"failed_units": []})

        restarted = []
        errors = []
        for unit in failed_units:
            restart_res = self.runner.run(["sudo", "systemctl", "restart", unit])
            if restart_res.exit_code == 0:
                restarted.append(unit)
            else:
                errors.append(f"{unit}: {restart_res.stderr}")

        summary = (
            f"Attempted to restart {len(failed_units)} services. "
            f"Successfully restarted: {', '.join(restarted) or 'none'}."
        )
        if errors:
            summary += f" Failures: {'; '.join(errors)}"

        return ToolOutput(summary=summary, data={"restarted": restarted, "errors": errors})
