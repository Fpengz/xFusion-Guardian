from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass


@dataclass(frozen=True)
class CommandResult:
    stdout: str
    stderr: str
    exit_code: int


class CommandRunner:
    """Runs bounded local commands with v0.2 runtime constraints."""

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
            return CommandResult(
                stdout=result.stdout[:max_stdout_bytes],
                stderr=result.stderr[:max_stderr_bytes],
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
