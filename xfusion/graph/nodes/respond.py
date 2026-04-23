from __future__ import annotations

from xfusion.domain.enums import ReasoningRole
from xfusion.graph.response import format_agent_response
from xfusion.graph.roles import record_role_proposal
from xfusion.graph.state import AgentGraphState


def respond_node(state: AgentGraphState) -> AgentGraphState:
    """Format final or intermediate response."""
    if not state.plan:
        return state

    record_role_proposal(
        state,
        role=ReasoningRole.EXPLANATION,
        proposal_type="audit_summary",
        payload={
            "plan_id": state.plan.plan_id,
            "latest_status": state.audit_records[-1].get("status") if state.audit_records else None,
            "repair_count": len(state.repair_proposals),
        },
        deterministic_layer="respond_node",
        consumes_redacted_inputs_only=True,
    )
    state.response = format_agent_response(state)
    return state
