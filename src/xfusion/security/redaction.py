from __future__ import annotations

import re
from typing import Any

REDACTION_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("aws_access_key", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    (
        "private_key_block",
        re.compile(
            r"-----BEGIN [A-Z ]*PRIVATE KEY-----.*?-----END [A-Z ]*PRIVATE KEY-----",
            re.DOTALL,
        ),
    ),
    ("bearer_token", re.compile(r"\bBearer\s+[A-Za-z0-9._~+/=-]{16,}\b")),
    (
        "assignment_secret",
        re.compile(
            r"(?i)\b(api[_-]?key|token|secret|password|passwd|credential)"
            r"\s*=\s*['\"]?[^'\"\s]{4,}"
        ),
    ),
    (
        "json_secret",
        re.compile(
            r"(?i)(\"(?:api[_-]?key|token|secret|password|credential)\""
            r"\s*:\s*\")[^\"]+(\")"
        ),
    ),
)


def redact_text(value: str) -> tuple[str, dict[str, int]]:
    """Redact common credential shapes deterministically."""
    redacted = value
    counts: dict[str, int] = {}
    for name, pattern in REDACTION_PATTERNS:
        if name == "json_secret":
            redacted, count = pattern.subn(r"\1[REDACTED]\2", redacted)
        elif name == "assignment_secret":
            redacted, count = pattern.subn(lambda m: f"{m.group(1)}=[REDACTED]", redacted)
        else:
            redacted, count = pattern.subn("[REDACTED]", redacted)
        if count:
            counts[name] = counts.get(name, 0) + count
    return redacted, counts


def redact_value(value: Any) -> tuple[Any, dict[str, Any]]:
    """Redact nested structures before model, user, or general audit exposure."""
    if isinstance(value, str):
        redacted, counts = redact_text(value)
        return redacted, {"redacted": bool(counts), "counts": counts}
    if isinstance(value, list):
        items = []
        totals: dict[str, int] = {}
        for item in value:
            redacted_item, meta = redact_value(item)
            items.append(redacted_item)
            for key, count in dict(meta.get("counts", {})).items():
                totals[key] = totals.get(key, 0) + int(count)
        return items, {"redacted": bool(totals), "counts": totals}
    if isinstance(value, dict):
        obj = {}
        totals: dict[str, int] = {}
        for key, item in value.items():
            redacted_item, meta = redact_value(item)
            obj[key] = redacted_item
            for pattern_name, count in dict(meta.get("counts", {})).items():
                totals[pattern_name] = totals.get(pattern_name, 0) + int(count)
        return obj, {"redacted": bool(totals), "counts": totals}
    return value, {"redacted": False, "counts": {}}
