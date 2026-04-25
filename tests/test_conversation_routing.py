from __future__ import annotations

import logging
from copy import deepcopy
from typing import Any

import pytest

from xfusion.app.turns import handle_user_turn
from xfusion.conversation.gateway import ClarificationResponse, IntentDecision
from xfusion.domain.models.environment import EnvironmentState


class FakeGateway:
    def __init__(self, decision: IntentDecision) -> None:
        self.decision = decision

    def classify(self, user_input: str, *, language: str = "en") -> IntentDecision:
        return self.decision


class FakeGraph:
    def __init__(self) -> None:
        self.calls = 0

    def invoke(self, state: dict[str, Any]) -> dict[str, Any]:
        self.calls += 1
        next_state = dict(state)
        next_state["response"] = "operational response"
        next_state["graph_called"] = True
        return next_state


def _state(user_input: str) -> dict[str, Any]:
    return {
        "user_input": user_input,
        "environment": EnvironmentState(),
        "language": "en",
        "plan": None,
        "current_step_id": None,
        "policy_decision": None,
        "verification_result": None,
        "last_tool_output": None,
        "step_outputs": {},
        "authorized_step_outputs": {},
        "pending_confirmation_phrase": None,
        "response": "",
        "audit_records": [],
    }


def test_conversational_turn_does_not_call_graph_or_mutate_state() -> None:
    state = _state("hi")
    original = deepcopy(state)
    graph = FakeGraph()
    gateway = FakeGateway(
        IntentDecision(
            mode="conversational",
            requires_execution=False,
            confidence=0.95,
            rationale="Greeting.",
        )
    )

    result = handle_user_turn(state, graph, gateway)

    assert graph.calls == 0
    assert state == original
    assert result.state == original
    assert result.decision.mode == "conversational"
    assert result.requires_execution is False
    assert result.execution_pipeline_called is False
    assert result.response.plan is None
    assert result.response.audit_records == []
    assert result.response.execution_surface is None


def test_clarify_turn_returns_structured_response_without_graph_or_state_mutation() -> None:
    state = _state("delete that file")
    original = deepcopy(state)
    graph = FakeGraph()
    clarification = ClarificationResponse(
        question="Which file should I delete?",
        missing_fields=["path"],
        risk_hint="Deletion requires an exact path.",
    )
    gateway = FakeGateway(
        IntentDecision(
            mode="clarify",
            requires_execution=False,
            confidence=0.9,
            rationale="Missing target.",
            clarification=clarification,
        )
    )

    result = handle_user_turn(state, graph, gateway)

    assert graph.calls == 0
    assert state == original
    assert result.state == original
    assert result.response.clarification == clarification
    assert result.response.execution_surface is None
    assert result.response.audit_records == []
    assert "Which file should I delete?" in result.response.message
    assert "path" in result.response.message
    assert "Deletion requires an exact path." in result.response.message


def test_operational_turn_invokes_graph_once() -> None:
    state = _state("check disk usage")
    graph = FakeGraph()
    gateway = FakeGateway(
        IntentDecision(
            mode="operational",
            requires_execution=True,
            confidence=0.95,
            rationale="Clear operation.",
        )
    )

    result = handle_user_turn(state, graph, gateway)

    assert graph.calls == 1
    assert result.requires_execution is True
    assert result.execution_pipeline_called is True
    assert result.state["graph_called"] is True


def test_requires_execution_flag_alone_cannot_enter_graph_for_non_operational_mode() -> None:
    state = _state("ambiguous")
    graph = FakeGraph()
    decision = IntentDecision.model_construct(
        mode="clarify",
        requires_execution=True,
        confidence=0.95,
        rationale="Bypassed validation in test double.",
        clarification=ClarificationResponse(
            question="What target should I use?",
            missing_fields=["target"],
        ),
    )
    gateway = FakeGateway(decision)

    result = handle_user_turn(state, graph, gateway)

    assert graph.calls == 0
    assert result.requires_execution is False
    assert result.execution_pipeline_called is False


def test_turn_routing_logs_decision_and_pipeline_boundary(
    caplog: pytest.LogCaptureFixture,
) -> None:
    state = _state("hi")
    graph = FakeGraph()
    gateway = FakeGateway(
        IntentDecision(
            mode="conversational",
            requires_execution=False,
            confidence=0.95,
            rationale="Greeting.",
        )
    )

    with caplog.at_level(logging.DEBUG, logger="xfusion.app.turns"):
        handle_user_turn(state, graph, gateway)

    messages = "\n".join(record.getMessage() for record in caplog.records)
    assert "conversation_turn.classified" in messages
    assert "mode=conversational" in messages
    assert "conversation_turn.pipeline_skipped" in messages
