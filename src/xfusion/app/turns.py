from __future__ import annotations

import logging
from copy import deepcopy
from typing import Any, Protocol

from pydantic import BaseModel, ConfigDict, Field

from xfusion.conversation.gateway import ClarificationResponse, IntentDecision

logger = logging.getLogger(__name__)


class IntentClassifier(Protocol):
    def classify(self, user_input: str, *, language: str = "en") -> IntentDecision: ...


class GatewayTurnResponse(BaseModel):
    """Display-safe response for a user turn before or after orchestration."""

    model_config = ConfigDict(extra="forbid")

    mode: str
    message: str
    clarification: ClarificationResponse | None = None
    plan: object | None = None
    audit_records: list[dict[str, object]] = Field(default_factory=list)
    execution_surface: str | None = None


class UserTurnResult(BaseModel):
    """Result of routing one user turn through the gateway boundary."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    decision: IntentDecision
    state: dict[str, Any]
    response: GatewayTurnResponse
    requires_execution: bool
    execution_pipeline_called: bool


def handle_user_turn(
    state: dict[str, Any],
    graph: Any,
    gateway: IntentClassifier,
) -> UserTurnResult:
    """Classify and route a turn without mutating state for non-operational modes."""
    state_snapshot = deepcopy(state)
    decision = enforce_routing_safety(
        gateway.classify(
            str(state_snapshot.get("user_input", "")),
            language=str(state_snapshot.get("language", "en") or "en"),
        )
    )
    logger.debug(
        "conversation_turn.classified mode=%s requires_execution=%s confidence=%.3f",
        decision.mode,
        decision.requires_execution,
        decision.confidence,
    )

    if decision.mode != "operational" or not decision.requires_execution:
        logger.info(
            "conversation_turn.pipeline_skipped mode=%s requires_execution=%s",
            decision.mode,
            decision.requires_execution,
        )
        response = non_operational_response(decision)
        return UserTurnResult(
            decision=decision,
            state=state_snapshot,
            response=response,
            requires_execution=False,
            execution_pipeline_called=False,
        )

    logger.info("conversation_turn.pipeline_entered mode=operational requires_execution=true")
    next_state = graph.invoke(state)
    logger.debug(
        "conversation_turn.pipeline_completed response_present=%s audit_record_count=%d",
        bool(next_state.get("response")),
        len(next_state.get("audit_records", [])),
    )
    return UserTurnResult(
        decision=decision,
        state=next_state,
        response=GatewayTurnResponse(
            mode="operational",
            message=str(next_state.get("response", "")),
            plan=next_state.get("plan"),
            audit_records=list(next_state.get("audit_records", [])),
            execution_surface=_latest_execution_surface(next_state),
        ),
        requires_execution=True,
        execution_pipeline_called=True,
    )


def non_operational_response(decision: IntentDecision) -> GatewayTurnResponse:
    if decision.mode == "conversational":
        return GatewayTurnResponse(
            mode="conversational",
            message="Hi. I can help with bounded Linux operations when you give me a clear task.",
        )

    clarification = decision.clarification or IntentDecision.fail_closed().clarification
    assert clarification is not None
    return GatewayTurnResponse(
        mode="clarify",
        message=_format_clarification_message(clarification),
        clarification=clarification,
    )


def _format_clarification_message(clarification: ClarificationResponse) -> str:
    lines = ["# Action Required", "", clarification.question]
    if clarification.missing_fields:
        fields = ", ".join(f"`{field}`" for field in clarification.missing_fields)
        lines.extend(["", f"Missing: {fields}"])
    if clarification.risk_hint:
        lines.extend(["", f"Risk hint: {clarification.risk_hint}"])
    return "\n".join(lines)


def _latest_execution_surface(state: dict[str, Any]) -> str | None:
    plan = state.get("plan")
    steps = getattr(plan, "steps", None)
    if not steps:
        return None
    for step in reversed(steps):
        surface = getattr(step, "execution_surface", None)
        if surface is not None:
            value = getattr(surface, "value", None)
            return str(value or surface)
    return None


def enforce_routing_safety(decision: IntentDecision) -> IntentDecision:
    if decision.mode == "operational" and decision.requires_execution:
        return decision
    if decision.mode in {"conversational", "clarify"} and not decision.requires_execution:
        return decision
    logger.warning(
        "conversation_turn.routing_safety_fail_closed mode=%s requires_execution=%s",
        decision.mode,
        decision.requires_execution,
    )
    return IntentDecision.fail_closed(
        rationale="Gateway decision had inconsistent execution routing fields."
    )
