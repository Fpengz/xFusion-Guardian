from __future__ import annotations

from pathlib import Path

from xfusion.domain.models.audit import AuditRecord


class JsonlAuditSink:
    """Append-only JSONL sink for validated audit records."""

    def __init__(self, path: str) -> None:
        self.path = Path(path)

    def write(self, record: AuditRecord) -> None:
        """Append one audit record."""
        with self.path.open("a", encoding="utf-8") as f:
            f.write(record.model_dump_json() + "\n")
