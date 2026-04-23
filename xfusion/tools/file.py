from __future__ import annotations

from pathlib import Path

from xfusion.execution.command_runner import CommandRunner
from xfusion.security.secrets import is_secret_path
from xfusion.tools.base import ToolOutput


class FileTools:
    """Scoped file inspection tools."""

    def __init__(self, runner: CommandRunner) -> None:
        self.runner = runner

    def search(self, query: str, path: str = ".", limit: int = 20) -> ToolOutput:
        """Search for files by name within a bounded result count."""
        safe_limit = max(1, min(limit, 50))
        res = self.runner.run(["find", path, "-iname", f"*{query}*", "-print"])
        if res.exit_code != 0:
            return ToolOutput(
                summary=f"File search failed: {res.stderr}", data={"error": res.stderr}
            )

        matches = res.stdout.splitlines()[:safe_limit]
        return ToolOutput(
            summary=f"Found {len(matches)} matching paths.",
            data={"matches": matches, "limit": safe_limit},
        )

    def preview_metadata(self, path: str) -> ToolOutput:
        """Return metadata for one path without reading file contents."""
        target = Path(path)
        if not target.exists():
            return ToolOutput(summary=f"{path} does not exist.", data={"exists": False})

        stat = target.stat()
        return ToolOutput(
            summary=f"Previewed metadata for {path}.",
            data={
                "exists": True,
                "path": str(target),
                "is_dir": target.is_dir(),
                "size_bytes": stat.st_size,
                "mtime": stat.st_mtime,
            },
        )

    def read_file(self, path: str, max_bytes: int = 4096) -> ToolOutput:
        """Read a bounded non-secret file snippet."""
        if is_secret_path(path):
            return ToolOutput(
                summary="Refusing to read known secret path.",
                data={"error": "secret_path"},
            )
        target = Path(path)
        if not target.exists() or not target.is_file():
            return ToolOutput(summary=f"{path} is not a readable file.", data={"error": "not_file"})
        data = target.read_text(errors="replace")[: max(0, min(max_bytes, 8192))]
        return ToolOutput(
            summary=f"Read bounded snippet from {path}.",
            data={
                "path": str(target),
                "content": data,
                "truncated": target.stat().st_size > len(data),
            },
        )
