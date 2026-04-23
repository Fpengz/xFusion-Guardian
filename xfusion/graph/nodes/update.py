from __future__ import annotations

from xfusion.domain.enums import InteractionState, StepStatus
from xfusion.graph.auditing import log_graph_event
from xfusion.graph.state import AgentGraphState


def _failed_steps_covered_by_active_repairs(state: AgentGraphState) -> set[str]:
    if not state.plan:
        return set()
    active_repairs = set(state.active_repair_step_ids)
    covered: set[str] = set()
    for proposal in state.repair_proposals:
        if proposal.state != "accepted_for_reentry":
            continue
        if proposal.draft.proposed_step_id in active_repairs:
            covered.add(proposal.original_step_id)
    return covered


def update_node(state: AgentGraphState) -> AgentGraphState:
    """Refresh environment/memory/audit state."""
    if not state.plan:
        return state

    dependency_abort = False
    covered_failures = _failed_steps_covered_by_active_repairs(state)
    if state.plan.interaction_state == InteractionState.EXECUTING and (
        any(
            s.status == StepStatus.FAILED and s.step_id not in covered_failures
            for s in state.plan.steps
        )
        or state.plan.has_unexecutable_pending_steps()
    ):
        state.plan.interaction_state = InteractionState.FAILED
        state.plan.status = "failed"
        dependency_abort = state.plan.has_unexecutable_pending_steps()
        if dependency_abort:
            state.response = (
                f"{state.response}\nPlan execution aborted: one or more dependencies failed."
            )

    # Create audit record from authoritative post-transition state.
    if state.current_step_id:
        step = next(
            (
                candidate
                for candidate in state.plan.steps
                if candidate.step_id == state.current_step_id
            ),
            None,
        )
        if step:
            if step.status == StepStatus.SUCCESS:
                step.authorized_output_accepted = True
                state.authorized_step_outputs[step.step_id] = state.step_outputs.get(
                    step.step_id, {}
                )
                if step.step_id in state.active_repair_step_ids:
                    state.active_repair_step_ids = [
                        repair_step_id
                        for repair_step_id in state.active_repair_step_ids
                        if repair_step_id != step.step_id
                    ]
            audit_status = step.failure_class or str(step.status)
            log_graph_event(
                state,
                step=step,
                status=audit_status,
                summary=state.response,
            )

    # Check if plan is complete.
    if state.plan.interaction_state == InteractionState.EXECUTING and all(
        s.status == StepStatus.SUCCESS for s in state.plan.steps
    ):
        state.plan.interaction_state = InteractionState.COMPLETED
        state.plan.status = "completed"

    return state
