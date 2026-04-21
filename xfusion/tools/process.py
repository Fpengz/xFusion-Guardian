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

    def kill(self, pid: int, signal: int = 15, port: int | None = None) -> ToolOutput:
        """Send signal to a resolved PID."""
        res = self.runner.run(["kill", f"-{signal}", str(pid)])
        if res.exit_code == 0:
            return ToolOutput(
                summary=f"Sent signal {signal} to PID {pid}.",
                data={"pid": pid, "signal": signal, "port": port},
            )
        return ToolOutput(
            summary=f"Failed to kill PID {pid}: {res.stderr}", data={"error": res.stderr}
        )
