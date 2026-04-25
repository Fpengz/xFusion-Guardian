from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class NormalizedOutput:
    valid: bool
    data: dict[str, Any]
    error: str | None = None


def _cast(value: str, cast_type: str) -> Any:
    if cast_type == "integer":
        return int(value)
    if cast_type == "number":
        return float(value)
    if cast_type == "boolean":
        return value.lower() in {"1", "true", "yes", "on"}
    return value


def normalize_output(
    *,
    stdout: str,
    stderr: str,
    exit_code: int,
    normalizer: dict[str, Any],
) -> NormalizedOutput:
    normalizer_type = str(normalizer.get("type", ""))
    try:
        if normalizer_type == "exit_status":
            return NormalizedOutput(valid=True, data={"ok": exit_code == 0, "exit_code": exit_code})
        if normalizer_type == "json":
            parsed = json.loads(stdout)
            if not isinstance(parsed, dict):
                return NormalizedOutput(valid=False, data={}, error="json output is not an object")
            return NormalizedOutput(valid=True, data=parsed)
        if normalizer_type == "line_list":
            return NormalizedOutput(
                valid=True,
                data={"lines": [line for line in stdout.splitlines() if line]},
            )
        if normalizer_type == "key_value":
            data: dict[str, str] = {}
            for line in stdout.splitlines():
                if "=" not in line:
                    return NormalizedOutput(valid=False, data={}, error="key_value parse mismatch")
                key, value = line.split("=", 1)
                data[key.strip()] = value.strip()
            return NormalizedOutput(valid=True, data=data)
        if normalizer_type == "regex_named_groups":
            pattern = str(normalizer.get("pattern", ""))
            match = re.search(pattern, stdout, flags=re.MULTILINE)
            if not match:
                return NormalizedOutput(valid=False, data={}, error="regex did not match")
            data = dict(match.groupdict())
            casts = normalizer.get("casts", {})
            if isinstance(casts, dict):
                for field, cast_type in casts.items():
                    if field in data:
                        data[str(field)] = _cast(data[str(field)], str(cast_type))
            return NormalizedOutput(valid=True, data=data)
    except Exception as exc:  # noqa: BLE001 - normalization must fail closed.
        return NormalizedOutput(valid=False, data={}, error=str(exc))
    return NormalizedOutput(
        valid=False,
        data={},
        error=f"unsupported normalizer '{normalizer_type}'",
    )
