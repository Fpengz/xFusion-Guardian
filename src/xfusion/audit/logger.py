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
        step_started_at: datetime | None,
        step_ended_at: datetime | None,
        status: str,
        summary: str,
        execution_surface: str | None = None,
        policy_category: str | None = None,
        final_risk_category: str | None = None,
        impact_scope: dict[str, object] | None = None,
        agent_risk_assessment: dict[str, object] | None = None,
        system_risk_envelope: dict[str, object] | None = None,
        resolution_record: dict[str, object] | None = None,
        fallback_reason: str | None = None,
        integrity_hashes: dict[str, object] | None = None,
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
            step_started_at=step_started_at,
            step_ended_at=step_ended_at,
            status=status,
            summary=summary,
            execution_surface=execution_surface,
            policy_category=policy_category,
            final_risk_category=final_risk_category,
            impact_scope=impact_scope or {},
            agent_risk_assessment=agent_risk_assessment or {},
            system_risk_envelope=system_risk_envelope or {},
            resolution_record=resolution_record or {},
            fallback_reason=fallback_reason,
            integrity_hashes=integrity_hashes or {},
        )
        self.sink.write(record)
