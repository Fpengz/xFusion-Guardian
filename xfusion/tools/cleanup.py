from __future__ import annotations

from xfusion.execution.command_runner import CommandRunner
from xfusion.policy.protected_paths import is_protected
from xfusion.tools.base import ToolOutput


class CleanupTools:
    """Bounded safe-cleanup tool surface."""

    def __init__(self, runner: CommandRunner) -> None:
        self.runner = runner

    def safe_disk_cleanup(self, path: str = "/tmp", limit: int = 20) -> ToolOutput:
        """Preview approved cleanup candidates without broad shell passthrough."""
        if is_protected(path, ("/", "/etc", "/boot", "/usr", "/var/lib")):
            return ToolOutput(
                summary=f"Refusing cleanup of protected path {path}.",
                data={"error": "protected_path"},
            )

        safe_limit = max(1, min(limit, 50))
        res = self.runner.run(["find", path, "-maxdepth", "1", "-type", "f", "-print"])
        if res.exit_code != 0:
            return ToolOutput(
                summary=f"Cleanup preview failed: {res.stderr}", data={"error": res.stderr}
            )

        candidates = res.stdout.splitlines()[:safe_limit]
        return ToolOutput(
            summary=f"Previewed {len(candidates)} safe cleanup candidates in {path}.",
            data={"previewed_candidates": candidates, "deleted": [], "ok": True},
        )
