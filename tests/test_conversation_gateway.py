from __future__ import annotations

import json
import logging

import pytest

from xfusion.app.settings import Settings
from xfusion.conversation.gateway import (
    CLARIFY_MISSING_FIELDS,
    CONFIDENCE_THRESHOLD,
    ClarificationResponse,
    ConversationGateway,
    IntentDecision,
)


class FakeLLMClient:
    def __init__(self, response: str | Exception) -> None:
        self.response = response
        self.calls: list[tuple[str, str]] = []

    def complete(self, system_prompt: str, user_prompt: str, timeout: float = 20.0) -> str:
        self.calls.append((system_prompt, user_prompt))
        if isinstance(self.response, Exception):
            raise self.response
        return self.response


def _gateway(payload: dict[str, object]) -> ConversationGateway:
    return ConversationGateway(llm_client=FakeLLMClient(json.dumps(payload)))


def test_valid_conversational_decision_requires_no_execution() -> None:
    llm = FakeLLMClient(
        json.dumps(
            {
                "mode": "conversational",
                "requires_execution": False,
                "confidence": 0.91,
                "rationale": "Greeting only.",
            }
        )
    )
    decision = ConversationGateway(llm_client=llm).classify("hi")

    assert decision.mode == "conversational"
    assert decision.requires_execution is False
    assert decision.clarification is None
    assert llm.calls
    assert "User input: hi" in llm.calls[0][1]


def test_valid_operational_decision_requires_execution() -> None:
    decision = _gateway(
        {
            "mode": "operational",
            "requires_execution": True,
            "confidence": 0.93,
            "rationale": "Clear disk inspection request.",
        }
    ).classify("check disk usage")

    assert decision.mode == "operational"
    assert decision.requires_execution is True


def test_valid_clarify_decision_returns_structured_clarification() -> None:
    decision = _gateway(
        {
            "mode": "clarify",
            "requires_execution": False,
            "confidence": 0.88,
            "rationale": "Deletion target is missing.",
            "clarification": {
                "question": "Which file should I delete?",
                "missing_fields": ["path"],
                "risk_hint": "Deletion is destructive and requires an exact target.",
            },
        }
    ).classify("delete that file")

    assert decision.mode == "clarify"
    assert decision.requires_execution is False
    assert decision.clarification == ClarificationResponse(
        question="Which file should I delete?",
        missing_fields=["path"],
        risk_hint="Deletion is destructive and requires an exact target.",
    )


@pytest.mark.parametrize(
    "payload",
    [
        {
            "mode": "operational",
            "requires_execution": False,
            "confidence": 0.92,
            "rationale": "Inconsistent operational route.",
        },
        {
            "mode": "conversational",
            "requires_execution": True,
            "confidence": 0.92,
            "rationale": "Inconsistent chat route.",
        },
        {
            "mode": "clarify",
            "requires_execution": False,
            "confidence": 0.92,
            "rationale": "Clarify without structured question.",
        },
        {
            "mode": "operational",
            "requires_execution": True,
            "confidence": CONFIDENCE_THRESHOLD - 0.01,
            "rationale": "Low confidence.",
        },
        {"mode": "nonsense", "requires_execution": False, "confidence": 0.9, "rationale": "Bad."},
    ],
)
def test_invalid_or_uncertain_outputs_fail_closed_to_clarify(payload: dict[str, object]) -> None:
    decision = _gateway(payload).classify("ambiguous input")

    assert decision.mode == "clarify"
    assert decision.requires_execution is False
    assert decision.clarification is not None
    assert decision.clarification.missing_fields == [CLARIFY_MISSING_FIELDS]


@pytest.mark.parametrize("response", ["not json", "{", json.dumps({"mode": "operational"})])
def test_malformed_llm_output_fails_closed_to_clarify(response: str) -> None:
    decision = ConversationGateway(llm_client=FakeLLMClient(response)).classify("check disk")

    assert decision.mode == "clarify"
    assert decision.requires_execution is False
    assert decision.clarification is not None


def test_llm_exception_fails_closed_to_clarify() -> None:
    decision = ConversationGateway(llm_client=FakeLLMClient(RuntimeError("boom"))).classify("hi")

    assert decision.mode == "clarify"
    assert decision.requires_execution is False
    assert decision.clarification is not None


def test_runtime_gateway_requires_llm_configuration() -> None:
    settings = Settings(llm_base_url=None, llm_api_key=None, llm_model=None)

    decision = ConversationGateway.from_settings(settings).classify("check disk usage")

    assert decision == IntentDecision.configuration_required()


def test_runtime_gateway_does_not_guess_conversation_without_llm_configuration() -> None:
    settings = Settings(llm_base_url=None, llm_api_key=None, llm_model=None)

    decision = ConversationGateway.from_settings(settings).classify("hi")

    assert decision == IntentDecision.configuration_required()
    assert decision.mode == "clarify"
    assert decision.requires_execution is False


def test_gateway_logs_llm_request_and_output(caplog: pytest.LogCaptureFixture) -> None:
    llm = FakeLLMClient(
        json.dumps(
            {
                "mode": "conversational",
                "requires_execution": False,
                "confidence": 0.91,
                "rationale": "Greeting only.",
            }
        )
    )

    with caplog.at_level(logging.DEBUG, logger="xfusion.conversation.gateway"):
        ConversationGateway(llm_client=llm).classify("hi")

    messages = "\n".join(record.getMessage() for record in caplog.records)
    assert "conversation_gateway.llm_request" in messages
    assert "User input: hi" in messages
    assert "conversation_gateway.llm_output" in messages
    assert '"mode": "conversational"' in messages


def test_gateway_logs_fail_closed_reason(caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.WARNING, logger="xfusion.conversation.gateway"):
        ConversationGateway(llm_client=FakeLLMClient("{")).classify("hi")

    messages = "\n".join(record.getMessage() for record in caplog.records)
    assert "conversation_gateway.fail_closed" in messages
    assert "classification_error" in messages
