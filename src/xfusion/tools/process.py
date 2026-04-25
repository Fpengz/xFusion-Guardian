from __future__ import annotations

from xfusion.execution.command_runner import CommandRunner
from xfusion.tools.base import ToolOutput


class ProcessTools:
    """Tools for process and port management."""

    def __init__(self, runner: CommandRunner) -> None:
        self.runner = runner

    def find_by_port(self, port: int, expect_free: bool = False) -> ToolOutput:
        """Return processes listening on a requested port."""
        # Try lsof first, then netstat
        res = self.runner.run(["lsof", "-i", f":{port}", "-t"])
        if res.exit_code == 0 and res.stdout.strip():
            pids = res.stdout.strip().splitlines()
            return ToolOutput(
                summary=f"Found processes on port {port}: {', '.join(pids)}", data={"pids": pids}
            )

        res = self.runner.run(["ss", "-lptn", f"sport = :{port}"])
        if res.exit_code == 0 and port.__str__() in res.stdout:
            return ToolOutput(
                summary=f"Found activity on port {port}.", data={"stdout": res.stdout}
            )

        return ToolOutput(summary=f"No processes found on port {port}.", data={"pids": []})

    def list(self, limit: int = 20) -> ToolOutput:
        """Return a bounded process listing."""
        safe_limit = max(1, min(limit, 50))
        res = self.runner.run(["ps", "-eo", "pid,comm", "--no-headers"])
        if res.exit_code == 0:
            processes = res.stdout.splitlines()[:safe_limit]
            return ToolOutput(
                summary=f"Listed {len(processes)} processes.",
                data={"processes": processes, "limit": safe_limit},
            )
        return ToolOutput(
            summary=f"Failed to list processes: {res.stderr}", data={"error": res.stderr}
        )

    def kill(self, pid: int, signal: str = "TERM", port: int | None = None) -> ToolOutput:
        """Send signal to a resolved PID."""
        res = self.runner.run(["kill", f"-{signal}", str(pid)])
        if res.exit_code == 0:
            return ToolOutput(
                summary=f"Sent signal {signal} to PID {pid}.",
                data={"ok": True, "pid": pid, "signal": signal, "port": port},
            )
        return ToolOutput(
            summary=f"Failed to kill PID {pid}: {res.stderr}", data={"error": res.stderr}
        )

    def inspect(self, pid: int) -> ToolOutput:
        """Detailed inspection of a single PID."""
        res = self.runner.run(["ps", "-p", str(pid), "-o", "pid,ppid,user,stat,comm,args"])
        if res.exit_code == 0:
            return ToolOutput(
                summary=f"Inspected PID {pid}.",
                data={"pid": pid, "stdout": res.stdout},
            )
        return ToolOutput(
            summary=f"PID {pid} not found or not inspectable.",
            data={"error": res.stderr},
        )

    def zombie_procs(self) -> ToolOutput:
        """Find zombie (defunct) processes."""
        res = self.runner.run(["ps", "-eo", "state,pid,comm", "--no-headers"])
        if res.exit_code != 0:
            return ToolOutput(summary="Failed to list processes.", data={"error": res.stderr})

        zombies = [
            line.split(None, 1)[1] for line in res.stdout.splitlines() if line.startswith("Z")
        ]
        return ToolOutput(
            summary=f"Found {len(zombies)} zombie processes."
            if zombies
            else "No zombie processes found.",
            data={"zombies": zombies},
        )

    def terminate_by_name(self, name: str, signal: str = "TERM") -> ToolOutput:
        """Terminate processes by name pattern."""
        res = self.runner.run(["pkill", f"-{signal}", "-f", name])
        if res.exit_code == 0:
            return ToolOutput(
                summary=f"Sent signal {signal} to processes matching '{name}'.",
                data={"name": name, "signal": signal},
            )
        return ToolOutput(
            summary=f"No processes matching '{name}' found or pkill failed.",
            data={"error": res.stderr},
        )
