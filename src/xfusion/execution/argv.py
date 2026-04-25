from __future__ import annotations

from typing import Any

from xfusion.execution.allowlist import ExecutableRegistry, ExecutableRegistryError


class ArgvExecutionError(ValueError):
    """Raised when a compiled argv execution binding cannot be safely bound."""


def build_bound_argv(
    execution_binding: dict[str, Any],
    args: dict[str, Any],
    executables: ExecutableRegistry,
) -> list[str]:
    """Bind a compiled argv manifest using only static tokens and typed args."""

    if execution_binding.get("type") != "argv":
        raise ArgvExecutionError("execution binding is not argv")
    executable_id = str(execution_binding.get("executable", ""))
    try:
        argv = [executables.require(executable_id)]
    except ExecutableRegistryError as exc:
        raise ArgvExecutionError(str(exc)) from exc
    for raw_token in execution_binding.get("argv", []):
        if not isinstance(raw_token, dict):
            raise ArgvExecutionError("argv token must be an object")
        if set(raw_token) == {"value"}:
            value = str(raw_token["value"])
            if any(marker in value for marker in ("{{", "}}", "|", "&&", "||", ";")):
                raise ArgvExecutionError("argv value token contains forbidden shell semantics")
            argv.append(value)
            continue
        if set(raw_token) == {"arg"}:
            arg_name = str(raw_token["arg"])
            if arg_name not in args:
                raise ArgvExecutionError(f"missing argv arg binding '{arg_name}'")
            value = args[arg_name]
            if not isinstance(value, str | int | float | bool):
                raise ArgvExecutionError(f"argv arg binding '{arg_name}' must be scalar")
            argv.append(str(value))
            continue
        raise ArgvExecutionError("argv token must contain exactly value or arg")
    return argv
