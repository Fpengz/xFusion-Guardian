from __future__ import annotations

from difflib import get_close_matches
from pathlib import Path

from xfusion.execution.command_runner import CommandRunner
from xfusion.security.secrets import is_secret_path
from xfusion.tools.base import ToolOutput


class FileTools:
    """Scoped file inspection tools."""

    def __init__(self, runner: CommandRunner) -> None:
        self.runner = runner

    def _resolve_search_path(self, path: str) -> tuple[Path | None, list[str]]:
        raw = Path(path)
        candidates: list[Path] = [raw]
        if raw.is_absolute():
            relative = Path(path.lstrip("/"))
            if str(relative) not in {"", "."}:
                candidates.append(Path.cwd() / relative)
        else:
            candidates.append(Path.cwd() / raw)

        seen: set[Path] = set()
        for candidate in candidates:
            if candidate in seen:
                continue
            seen.add(candidate)

            if candidate.exists() and candidate.is_dir():
                return candidate, []

            resolved, corrections = self._resolve_with_fallback(candidate)
            if resolved is not None and resolved.exists() and resolved.is_dir():
                return resolved, corrections
        return None, []

    def _resolve_with_fallback(self, candidate: Path) -> tuple[Path | None, list[str]]:
        current = Path(candidate.anchor) if candidate.is_absolute() else Path(".")
        parts = [part for part in candidate.parts if part not in {"", "/", candidate.anchor}]
        corrections: list[str] = []

        for part in parts:
            exact = current / part
            if exact.exists():
                current = exact
                continue

            if not current.exists() or not current.is_dir():
                return None, []

            chosen = self._closest_child_name(current, part)
            if not chosen:
                return None, []
            corrections.append(f"{part}->{chosen}")
            current = current / chosen
        return current, corrections

    def _closest_child_name(self, parent: Path, expected: str) -> str | None:
        children = [child.name for child in parent.iterdir() if child.is_dir()]
        if not children:
            return None
        if f"{expected}s" in children:
            return f"{expected}s"
        if expected.endswith("s") and expected[:-1] in children:
            return expected[:-1]
        matches = get_close_matches(expected, children, n=1, cutoff=0.84)
        return matches[0] if matches else None

    def search(self, query: str, path: str = ".", limit: int = 20) -> ToolOutput:
        """Search for files by name within a bounded result count."""
        search_path, corrections = self._resolve_search_path(path)
        if search_path is None:
            return ToolOutput(
                summary=f"File search failed: path '{path}' does not exist.",
                data={"error": f"path_not_found:{path}"},
            )

        pattern = query.strip()
        if not pattern:
            return ToolOutput(
                summary="File search failed: empty query.",
                data={"error": "empty_query"},
            )

        safe_limit = max(1, min(limit, 50))
        if any(token in pattern for token in ("*", "?", "[")):
            find_pattern = pattern
        else:
            find_pattern = f"*{pattern}*"
        res = self.runner.run(["find", str(search_path), "-iname", find_pattern, "-print"])
        if res.exit_code != 0:
            return ToolOutput(
                summary=f"File search failed: {res.stderr}", data={"error": res.stderr}
            )

        matches = res.stdout.splitlines()[:safe_limit]
        correction_summary = ""
        if corrections:
            correction_summary = f" Path correction applied ({', '.join(corrections)})."
        return ToolOutput(
            summary=f"Found {len(matches)} matching paths in {search_path}.{correction_summary}",
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
