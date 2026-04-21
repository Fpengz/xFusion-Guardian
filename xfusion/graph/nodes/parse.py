from __future__ import annotations

from xfusion.graph.state import AgentGraphState


def parse_node(state: AgentGraphState) -> AgentGraphState:
    """Normalize language input and produce a parsed intent candidate."""
    # In v0.1, we use a simple parser or LLM to detect the intent.
    # For now, let's just assume we can detect the language.
    if any("\u4e00" <= c <= "\u9fff" for c in state.user_input):
        state.language = "zh"
    else:
        state.language = "en"

    return state
