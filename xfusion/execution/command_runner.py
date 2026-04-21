from __future__ import annotations

import subprocess
from dataclasses import dataclass


@dataclass(frozen=True)
class CommandResult:
    stdout: str
    stderr: str
    exit_code: int


class CommandRunner:
    """Runs bounded local commands with timeout and captured output."""

    def run(self, command: list[str], *, timeout: float = 30.0) -> CommandResult:
        """Run one non-interactive command."""
        try:
            result = subprocess.run(
                command,
                capture_output=True,
                text=True,
                timeout=timeout,
                check=False,
            )
            return CommandResult(
                stdout=result.stdout,
                stderr=result.stderr,
                exit_code=result.returncode,
            )
        except subprocess.TimeoutExpired as e:
            return CommandResult(
                stdout=e.stdout.decode() if e.stdout else "",
                stderr=f"Timeout expired after {timeout}s",
                exit_code=-1,
            )
        except Exception as e:
            return CommandResult(
                stdout="",
                stderr=str(e),
                exit_code=-1,
            )
