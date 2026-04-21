from __future__ import annotations

from datetime import datetime

from xfusion.audit.jsonl_sink import JsonlAuditSink
from xfusion.domain.models.audit import AuditRecord


class AuditLogger:
    """Orchestrates audit record creation and persistence."""

    def __init__(self, sink: JsonlAuditSink) -> None:
        self.sink = sink

    def log_step(
        self,
        plan_id: str,
        step_id: str,
        interaction_state: str,
        before_state: dict[str, object],
        action_taken: dict[str, object],
        after_state: dict[str, object],
        verification_result: dict[str, object],
        status: str,
        summary: str,
    ) -> None:
        """Create and write one audit record."""
        record = AuditRecord(
            timestamp=datetime.now(),
            plan_id=plan_id,
            step_id=step_id,
            interaction_state=interaction_state,
            before_state=before_state,
            action_taken=action_taken,
            after_state=after_state,
            verification_result=verification_result,
            status=status,
            summary=summary,
        )
        self.sink.write(record)
