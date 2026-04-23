from __future__ import annotations

import os
import subprocess
import time
from dataclasses import dataclass


@dataclass(frozen=True)
class CommandResult:
    stdout: str
    stderr: str
    exit_code: int


@dataclass(frozen=True)
class CommandTraceEntry:
    planned_argv: list[str]
    ran_argv: list[str]
    exit_code: int
    stdout_excerpt: str
    stderr_excerpt: str
    started_at: str
    ended_at: str
    duration_ms: int


class CommandRunner:
    """Runs bounded local commands with v0.2 runtime constraints."""

    def __init__(self) -> None:
        self._trace_session_active = False
        self._trace_entries: list[CommandTraceEntry] = []

    def begin_trace_session(self) -> None:
        """Start a command trace capture session for one tool execution."""
        self._trace_session_active = True
        self._trace_entries = []

    def end_trace_session(self) -> list[dict[str, object]]:
        """Close the active trace session and return normalized trace entries."""
        entries = [self._trace_entry_to_dict(entry) for entry in self._trace_entries]
        self._trace_session_active = False
        self._trace_entries = []
        return entries

    def _trace_entry_to_dict(self, entry: CommandTraceEntry) -> dict[str, object]:
        return {
            "planned_argv": entry.planned_argv,
            "ran_argv": entry.ran_argv,
            "exit_code": entry.exit_code,
            "stdout_excerpt": entry.stdout_excerpt,
            "stderr_excerpt": entry.stderr_excerpt,
            "started_at": entry.started_at,
            "ended_at": entry.ended_at,
            "duration_ms": entry.duration_ms,
        }

    def run(
        self,
        command: list[str],
        *,
        timeout: float = 30.0,
        max_stdout_bytes: int = 100_000,
        max_stderr_bytes: int = 100_000,
        cwd: str = ".",
        env: dict[str, str] | None = None,
    ) -> CommandResult:
        """Run one non-interactive command from a typed adapter.

        The runner never accepts shell text. It executes argument arrays with
        shell=False, no TTY, bounded environment, bounded cwd, timeout, and
        captured output limits.
        """
        if not command or any(not isinstance(part, str) or not part for part in command):
            return CommandResult(stdout="", stderr="Invalid command argv.", exit_code=-1)
        if command[0] in {"sh", "bash", "zsh", "python", "python3"}:
            return CommandResult(stdout="", stderr="Prohibited interpreter adapter.", exit_code=-1)
        bounded_env = {
            "PATH": os.environ.get("PATH", "/usr/bin:/bin:/usr/sbin:/sbin"),
            "LANG": os.environ.get("LANG", "C"),
        }
        if env:
            for key, value in env.items():
                if key in {"PATH", "LANG", "LC_ALL"}:
                    bounded_env[key] = value
        start_perf = time.perf_counter()
        start_time = time.strftime("%Y-%m-%dT%H:%M:%S%z")
        try:
            result = subprocess.run(
                command,
                shell=False,
                capture_output=True,
                text=True,
                timeout=timeout,
                check=False,
                cwd=cwd,
                env=bounded_env,
            )
            command_result = CommandResult(
                stdout=result.stdout[:max_stdout_bytes],
                stderr=result.stderr[:max_stderr_bytes],
                exit_code=result.returncode,
            )
            self._append_trace(
                planned_argv=command,
                ran_argv=command,
                result=command_result,
                started_at=start_time,
                start_perf=start_perf,
            )
            return command_result
        except subprocess.TimeoutExpired as e:
            command_result = CommandResult(
                stdout=e.stdout.decode() if e.stdout else "",
                stderr=f"Timeout expired after {timeout}s",
                exit_code=-1,
            )
            self._append_trace(
                planned_argv=command,
                ran_argv=command,
                result=command_result,
                started_at=start_time,
                start_perf=start_perf,
            )
            return command_result
        except Exception as e:
            command_result = CommandResult(
                stdout="",
                stderr=str(e),
                exit_code=-1,
            )
            self._append_trace(
                planned_argv=command,
                ran_argv=command,
                result=command_result,
                started_at=start_time,
                start_perf=start_perf,
            )
            return command_result

    def _append_trace(
        self,
        *,
        planned_argv: list[str],
        ran_argv: list[str],
        result: CommandResult,
        started_at: str,
        start_perf: float,
    ) -> None:
        if not self._trace_session_active:
            return
        duration_ms = max(0, int((time.perf_counter() - start_perf) * 1000))
        ended_at = time.strftime("%Y-%m-%dT%H:%M:%S%z")
        self._trace_entries.append(
            CommandTraceEntry(
                planned_argv=list(planned_argv),
                ran_argv=list(ran_argv),
                exit_code=result.exit_code,
                stdout_excerpt=result.stdout,
                stderr_excerpt=result.stderr,
                started_at=started_at,
                ended_at=ended_at,
                duration_ms=duration_ms,
            )
        )
