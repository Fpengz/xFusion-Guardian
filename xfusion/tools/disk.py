from __future__ import annotations

from xfusion.execution.command_runner import CommandRunner
from xfusion.tools.base import ToolOutput


class DiskTools:
    """Tools for disk usage and inspection."""

    def __init__(self, runner: CommandRunner) -> None:
        self.runner = runner

    def check_usage(self, path: str = "/") -> ToolOutput:
        """Report root filesystem usage."""
        res = self.runner.run(["df", "-h", path])
        if res.exit_code == 0:
            return ToolOutput(
                summary=f"Disk usage for {path}:\n{res.stdout}", data={"stdout": res.stdout}
            )
        return ToolOutput(
            summary=f"Failed to check disk usage: {res.stderr}", data={"error": res.stderr}
        )

    def find_large_directories(self, path: str, limit: int = 10) -> ToolOutput:
        """Run a bounded one-level directory size scan."""
        res = self.runner.run(["du", "-sh", f"{path.rstrip('/')}/*"])
        if res.exit_code == 0:
            lines = res.stdout.splitlines()
            # Sort by size would require more logic, but for now just return the list
            return ToolOutput(
                summary=f"Found {len(lines)} items in {path}.", data={"items": lines[:limit]}
            )
        return ToolOutput(
            summary=f"Failed to find large directories: {res.stderr}", data={"error": res.stderr}
        )
