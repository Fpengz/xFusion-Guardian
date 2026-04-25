from __future__ import annotations

import shutil
import time
from pathlib import Path

from xfusion.execution.command_runner import CommandRunner
from xfusion.policy.protected_paths import is_protected
from xfusion.tools.base import ToolOutput


class CleanupTools:
    """Bounded safe-cleanup tool surface."""

    def __init__(self, runner: CommandRunner) -> None:
        self.runner = runner

    def safe_disk_cleanup(
        self,
        approved_paths: list[str] | None = None,
        candidate_class: str = "demo_cache",
        older_than_days: int = 0,
        max_files: int = 20,
        max_bytes: int = 50_000_000,
        execute: bool = False,
        path: str | None = None,
        limit: int | None = None,
    ) -> ToolOutput:
        """Preview or delete explicitly approved cleanup candidates."""
        if approved_paths is None:
            approved_paths = [path or "/tmp"]
        if limit is not None:
            max_files = limit

        protected = ("/", "/etc", "/boot", "/usr", "/var/lib")
        for approved_path in approved_paths:
            if is_protected(approved_path, protected):
                return ToolOutput(
                    summary=f"Refusing cleanup of protected path {approved_path}.",
                    data={"error": "protected_path", "path": approved_path},
                )

        candidates = self._find_candidates(
            approved_paths=approved_paths,
            candidate_class=candidate_class,
            older_than_days=older_than_days,
            max_files=max_files,
            max_bytes=max_bytes,
        )

        if not execute:
            return ToolOutput(
                summary=f"Previewed {len(candidates)} safe cleanup candidates.",
                data={
                    "previewed_candidates": candidates,
                    "deleted": [],
                    "reclaimed_bytes": 0,
                    "ok": True,
                },
            )

        deleted: list[str] = []
        reclaimed_bytes = 0
        for candidate in candidates:
            target = Path(str(candidate["path"]))
            raw_size = candidate["size_bytes"]
            size = raw_size if isinstance(raw_size, int) else int(str(raw_size))
            try:
                if target.is_dir() and not target.is_symlink():
                    shutil.rmtree(target)
                else:
                    target.unlink()
            except FileNotFoundError:
                pass
            deleted.append(str(target))
            reclaimed_bytes += size

        return ToolOutput(
            summary=f"Deleted {len(deleted)} safe cleanup candidates.",
            data={
                "previewed_candidates": candidates,
                "deleted": deleted,
                "reclaimed_bytes": reclaimed_bytes,
                "ok": True,
            },
        )

    def _find_candidates(
        self,
        *,
        approved_paths: list[str],
        candidate_class: str,
        older_than_days: int,
        max_files: int,
        max_bytes: int,
    ) -> list[dict[str, object]]:
        cutoff = time.time() - (older_than_days * 86_400)
        candidates: list[dict[str, object]] = []
        remaining_bytes = max_bytes

        for approved_path in approved_paths:
            root = Path(approved_path)
            if not root.exists() or not root.is_dir():
                continue
            patterns = _patterns_for_class(candidate_class)
            for pattern in patterns:
                for target in root.glob(pattern):
                    if len(candidates) >= max_files or remaining_bytes <= 0:
                        return candidates
                    if target.is_symlink() or not _is_safe_candidate(target, candidate_class):
                        continue
                    try:
                        stat = target.stat()
                    except OSError:
                        continue
                    if stat.st_mtime > cutoff:
                        continue
                    size = _size_bytes(target)
                    if size > remaining_bytes:
                        continue
                    candidates.append(
                        {
                            "path": str(target),
                            "size_bytes": size,
                            "candidate_class": candidate_class,
                        }
                    )
                    remaining_bytes -= size

        return candidates


def _patterns_for_class(candidate_class: str) -> list[str]:
    if candidate_class == "demo_cache":
        return ["xfusion-demo-*"]
    if candidate_class == "temp":
        return ["xfusion-demo-*", "*.tmp"]
    if candidate_class == "rotated_logs":
        return ["*.gz", "*.1", "*.old"]
    if candidate_class == "apt_cache":
        return ["*.deb"]
    return ["xfusion-demo-*"]


def _is_safe_candidate(target: Path, candidate_class: str) -> bool:
    name = target.name
    if candidate_class in {"demo_cache", "temp"}:
        return name.startswith("xfusion-demo-") or name.endswith(".tmp")
    if candidate_class == "rotated_logs":
        return name.endswith((".gz", ".1", ".old"))
    if candidate_class == "apt_cache":
        return name.endswith(".deb")
    return False


def _size_bytes(target: Path) -> int:
    if target.is_file():
        return target.stat().st_size
    if target.is_dir():
        return sum(path.stat().st_size for path in target.rglob("*") if path.is_file())
    return 0
