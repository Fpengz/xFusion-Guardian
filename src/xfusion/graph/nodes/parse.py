from __future__ import annotations

from xfusion.domain.enums import ReasoningRole
from xfusion.graph.roles import record_role_proposal
from xfusion.graph.state import AgentGraphState


def parse_node(state: AgentGraphState) -> AgentGraphState:
    """Normalize language input and produce a parsed intent candidate."""
    # Keep request interpretation non-authoritative; validation and policy own safety.
    if any("\u4e00" <= c <= "\u9fff" for c in state.user_input):
        state.language = "zh"
    else:
        state.language = "en"

    record_role_proposal(
        state,
        role=ReasoningRole.SUPERVISOR,
        proposal_type="intent",
        payload={"goal": state.user_input, "language": state.language},
        deterministic_layer="parse_node",
        consumes_redacted_inputs_only=True,
    )

    return state
