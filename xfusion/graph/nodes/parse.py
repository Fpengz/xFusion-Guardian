from __future__ import annotations

from xfusion.graph.state import AgentGraphState


def parse_node(state: AgentGraphState) -> AgentGraphState:
    """Normalize language input and produce a parsed intent candidate."""
    # Keep request interpretation non-authoritative; validation and policy own safety.
    if any("\u4e00" <= c <= "\u9fff" for c in state.user_input):
        state.language = "zh"
    else:
        state.language = "en"

    return state
