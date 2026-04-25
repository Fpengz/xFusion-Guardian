from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from xfusion.app.settings import Settings
from xfusion.llm.client import LLMClient
from xfusion.prompts import PromptContext, PromptRegistry, build_prompt
from xfusion.prompts.prompt_composer import PromptBuildResult
from xfusion.prompts.prompt_registry import PromptRegistryError
from xfusion.security.redaction import redact_text

logger = logging.getLogger(__name__)

IntentMode = Literal["conversational", "operational", "clarify"]

CONFIDENCE_THRESHOLD = 0.75
CLARIFY_MISSING_FIELDS = "intent"
DEFAULT_CLARIFICATION_QUESTION = (
    "I need one more detail before I can decide whether this should run. "
    "What target, scope, or action do you want XFusion to use?"
)
CONFIGURATION_REQUIRED_QUESTION = (
    "Conversation routing requires XFusion LLM configuration before I can execute. "
    "Please configure XFUSION_LLM_BASE_URL, XFUSION_LLM_API_KEY, and XFUSION_LLM_MODEL."
)


class ClarificationResponse(BaseModel):
    """Structured clarification payload returned before orchestration."""

    model_config = ConfigDict(extra="forbid")

    question: str = Field(min_length=1)
    missing_fields: list[str] = Field(default_factory=list)
    risk_hint: str | None = None


class IntentDecision(BaseModel):
    """Conversation gateway decision for one user turn."""

    model_config = ConfigDict(extra="forbid")

    mode: IntentMode
    requires_execution: bool
    confidence: float = Field(ge=0.0, le=1.0)
    rationale: str = Field(min_length=1)
    clarification: ClarificationResponse | None = None
    prompt_build: PromptBuildResult | None = None

    @model_validator(mode="after")
    def enforce_execution_contract(self) -> IntentDecision:
        if self.mode == "operational" and not self.requires_execution:
            raise ValueError("operational decisions must require execution")
        if self.mode in {"conversational", "clarify"} and self.requires_execution:
            raise ValueError("non-operational decisions must not require execution")
        if self.mode == "clarify" and self.clarification is None:
            raise ValueError("clarify decisions require structured clarification")
        if self.mode != "clarify" and self.clarification is not None:
            raise ValueError("only clarify decisions may include clarification")
        return self

    @classmethod
    def fail_closed(
        cls,
        *,
        question: str = DEFAULT_CLARIFICATION_QUESTION,
        missing_fields: list[str] | None = None,
        risk_hint: str | None = "Uncertain intent cannot enter the execution pipeline.",
        rationale: str = "Gateway could not confidently classify the request.",
        prompt_build: PromptBuildResult | None = None,
    ) -> IntentDecision:
        return cls(
            mode="clarify",
            requires_execution=False,
            confidence=0.0,
            rationale=rationale,
            clarification=ClarificationResponse(
                question=question,
                missing_fields=missing_fields or [CLARIFY_MISSING_FIELDS],
                risk_hint=risk_hint,
            ),
            prompt_build=prompt_build,
        )

    @classmethod
    def configuration_required(cls) -> IntentDecision:
        return cls.fail_closed(
            question=CONFIGURATION_REQUIRED_QUESTION,
            missing_fields=["llm_base_url", "llm_api_key", "llm_model"],
            risk_hint="Execution routing is disabled until the gateway classifier is configured.",
            rationale="LLM configuration is missing.",
        )


class ConversationGateway:
    """Pre-orchestration routing layer with LLM-assisted classification."""

    def __init__(
        self,
        llm_client: Any | None = None,
        *,
        config_missing: bool = False,
        prompts_root: str | Path | None = None,
    ) -> None:
        self.llm_client = llm_client
        self.config_missing = config_missing
        self.prompt_registry = PromptRegistry(prompts_root) if prompts_root else None

    @classmethod
    def from_settings(cls, settings: Settings) -> ConversationGateway:
        if not settings.llm_base_url or not settings.llm_api_key or not settings.llm_model:
            return cls(config_missing=True)
        return cls(llm_client=LLMClient(settings))

    def classify(self, user_input: str, *, language: str = "en") -> IntentDecision:
        logger.debug(
            "conversation_gateway.classify_start language=%s input_length=%d "
            "config_missing=%s has_llm_client=%s",
            language,
            len(user_input),
            self.config_missing,
            self.llm_client is not None,
        )
        if self.config_missing or self.llm_client is None:
            logger.warning("conversation_gateway.config_missing requires_execution=false")
            return IntentDecision.configuration_required()

        redacted_input, _meta = redact_text(user_input)
        try:
            prompt_build = build_prompt(
                ctx=PromptContext(
                    step_type="planning",
                    capability=None,
                    risk_level="low",
                    project_context={"prompt_targets": ["gateway"]},
                ),
                registry=self.prompt_registry,
            )
        except (PromptRegistryError, ValueError):
            logger.warning(
                "conversation_gateway.fail_closed reason=prompt_build_error",
                exc_info=True,
            )
            return IntentDecision.fail_closed(
                rationale="Gateway prompt construction failed.",
                risk_hint="Execution routing is disabled until prompt construction succeeds.",
            )

        system_prompt = prompt_build.system_prompt
        user_prompt = (
            f"Language: {language}\n"
            f"User input: {redacted_input}\n\n"
            "Return only JSON matching the IntentDecision contract."
        )
        logger.debug(
            "conversation_gateway.llm_request system_prompt=%s user_prompt=%s",
            system_prompt,
            user_prompt,
        )

        try:
            raw = self.llm_client.complete(system_prompt, user_prompt, timeout=15.0)
            redacted_raw, _raw_meta = redact_text(raw)
            logger.debug("conversation_gateway.llm_output raw=%s", redacted_raw)
            payload = _parse_json_object(raw)
            logger.debug("conversation_gateway.parsed_output keys=%s", sorted(payload.keys()))
            decision = IntentDecision.model_validate({**payload, "prompt_build": prompt_build})
        except (ValidationError, ValueError, TypeError, json.JSONDecodeError, KeyError):
            logger.warning(
                "conversation_gateway.fail_closed reason=classification_error",
                exc_info=True,
            )
            return IntentDecision.fail_closed(prompt_build=prompt_build)
        except Exception:
            logger.warning(
                "conversation_gateway.fail_closed reason=llm_error",
                exc_info=True,
            )
            return IntentDecision.fail_closed(prompt_build=prompt_build)

        if decision.confidence < CONFIDENCE_THRESHOLD:
            logger.warning(
                "conversation_gateway.fail_closed reason=low_confidence mode=%s "
                "requires_execution=%s confidence=%.3f threshold=%.3f",
                decision.mode,
                decision.requires_execution,
                decision.confidence,
                CONFIDENCE_THRESHOLD,
            )
            question = (
                decision.clarification.question
                if decision.clarification
                else DEFAULT_CLARIFICATION_QUESTION
            )
            missing_fields = (
                decision.clarification.missing_fields
                if decision.clarification
                else [CLARIFY_MISSING_FIELDS]
            )
            risk_hint = (
                decision.clarification.risk_hint
                if decision.clarification
                else "Classifier confidence was below the execution threshold."
            )
            return IntentDecision.fail_closed(
                question=question,
                missing_fields=missing_fields,
                risk_hint=risk_hint,
                rationale=(
                    f"Gateway confidence {decision.confidence:.2f} is below "
                    f"{CONFIDENCE_THRESHOLD:.2f}."
                ),
                prompt_build=prompt_build,
            )

        logger.info(
            "conversation_gateway.decision mode=%s requires_execution=%s confidence=%.3f",
            decision.mode,
            decision.requires_execution,
            decision.confidence,
        )
        return decision


def _parse_json_object(raw: str) -> dict[str, Any]:
    text = raw.strip()
    if text.startswith("```json"):
        text = text[7:]
    elif text.startswith("```"):
        text = text[3:]
    if text.endswith("```"):
        text = text[:-3]
    parsed = json.loads(text.strip())
    if not isinstance(parsed, dict):
        raise ValueError("gateway output must be a JSON object")
    return parsed
