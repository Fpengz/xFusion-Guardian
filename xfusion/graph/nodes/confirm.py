from __future__ import annotations

from datetime import UTC, datetime

from xfusion.domain.enums import FailureClass, InteractionState
from xfusion.graph.auditing import log_graph_event
from xfusion.graph.state import AgentGraphState


def confirm_node(state: AgentGraphState) -> AgentGraphState:
    """Handle pause for exact typed confirmation when required."""
    if not state.plan or state.plan.interaction_state != InteractionState.AWAITING_CONFIRMATION:
        return state

    step = state.plan.next_executable_step()
    if not step:
        return state

    expected = (step.confirmation_phrase or "").strip()
    actual = state.user_input.strip()
    approval = state.approval_records.get(state.pending_approval_id or step.approval_id or "")

    if expected and approval and actual == expected and not approval.is_expired():
        approval.approved_at = datetime.now(UTC)
        state.plan.interaction_state = InteractionState.EXECUTING
        step.requires_confirmation = False
        state.response = "Confirmation received. Proceeding..."
        log_graph_event(
            state,
            step=step,
            status="approval_granted",
            summary=state.response,
            action_taken={"approval_response": approval.model_dump(mode="json")},
        )
    else:
        state.plan.interaction_state = InteractionState.ABORTED
        state.plan.status = "aborted"
        reason = "approval_expired" if approval and approval.is_expired() else "phrase_mismatch"
        step.failure_class = (
            FailureClass.APPROVAL_EXPIRED.value
            if reason == "approval_expired"
            else FailureClass.APPROVAL_DENIED.value
        )
        step.failure_details = {
            "failure_class": step.failure_class,
            "approval_id": approval.approval_id if approval else None,
            "reason": reason,
        }
        state.response = f"Action aborted: approval failed ({reason})."
        if approval:
            approval.invalidated_at = datetime.now(UTC)
            approval.invalidation_reason = reason
        log_graph_event(
            state,
            step=step,
            status="approval_denied",
            summary=state.response,
            action_taken={
                "approval_id": approval.approval_id if approval else None,
                "reason": reason,
            },
        )

    # Requirements: Confirmation must be cleared after one use.
    state.pending_confirmation_phrase = None
    state.pending_approval_id = None
    step.confirmation_phrase = None

    return state
