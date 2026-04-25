from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from xfusion.capabilities.registry import CapabilityRegistry
from xfusion.domain.models.capability import CapabilityDefinition

TOKEN_RE = re.compile(r"[a-z0-9]+")


@dataclass(frozen=True)
class RetrievalHistory:
    successes: dict[str, int] = field(default_factory=dict)
    failures: dict[str, int] = field(default_factory=dict)
    last_used_rank: dict[str, int] = field(default_factory=dict)


@dataclass(frozen=True)
class RetrievalAvailability:
    unavailable: dict[str, str] = field(default_factory=dict)


class CapabilityCandidate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    short_description: str
    risk_tier: str
    side_effect_classification: str
    capability_confidence: float = Field(ge=0.0, le=1.0)
    ranking_signals: dict[str, float]
    why_selected: str
    rejected_alternatives: list[dict[str, str | float]] = Field(default_factory=list)


class CapabilityRetrievalResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    candidates: list[CapabilityCandidate]


class CapabilityRetriever:
    """Rank capabilities while exposing only a minimal surface to the agent."""

    def __init__(
        self,
        registry: CapabilityRegistry,
        *,
        history: RetrievalHistory | None = None,
        availability: RetrievalAvailability | None = None,
    ) -> None:
        self.registry = registry
        self.history = history or RetrievalHistory()
        self.availability = availability or RetrievalAvailability()

    def retrieve(
        self,
        intent: str,
        *,
        top_k: int = 10,
        filters: dict[str, Any] | None = None,
    ) -> CapabilityRetrievalResult:
        filters = filters or {}
        scored: list[tuple[float, CapabilityCandidate]] = []
        for capability in self.registry.all():
            if not self._matches_filters(capability, filters):
                continue
            signals = self._ranking_signals(intent, capability)
            score = _weighted_score(signals)
            confidence = max(0.0, min(1.0, score))
            candidate = CapabilityCandidate(
                name=capability.name,
                short_description=capability.short_description,
                risk_tier=str(capability.risk_tier),
                side_effect_classification=capability.side_effect_classification,
                capability_confidence=confidence,
                ranking_signals=signals,
                why_selected=(
                    "Selected because it matched the request intent, platform/risk filters, "
                    f"and ranked with confidence {confidence:.2f}."
                ),
            )
            scored.append((score, candidate))
        scored.sort(key=lambda item: item[0], reverse=True)
        candidates = [candidate for _, candidate in scored[:top_k]]
        for index, candidate in enumerate(candidates):
            rejected = [
                {
                    "name": other.name,
                    "capability_confidence": other.capability_confidence,
                    "reason": _rejection_reason(other),
                }
                for other in candidates[index + 1 : index + 4]
            ]
            candidates[index] = candidate.model_copy(update={"rejected_alternatives": rejected})
        return CapabilityRetrievalResult(candidates=candidates)

    def _matches_filters(
        self,
        capability: CapabilityDefinition,
        filters: dict[str, Any],
    ) -> bool:
        category = filters.get("category")
        if category and not capability.name.startswith(f"{category}."):
            return False
        risk = filters.get("risk_tier")
        if risk and str(capability.risk_tier) != str(risk):
            return False
        side_effect = filters.get("side_effect_classification")
        return not (side_effect and capability.side_effect_classification != side_effect)

    def _ranking_signals(
        self,
        intent: str,
        capability: CapabilityDefinition,
    ) -> dict[str, float]:
        intent_tokens = set(TOKEN_RE.findall(intent.lower()))
        searchable_text = f"{capability.name} {capability.short_description}".lower()
        capability_tokens = set(TOKEN_RE.findall(searchable_text))
        overlap = len(intent_tokens & capability_tokens)
        semantic_similarity = overlap / max(1, len(intent_tokens | capability_tokens))
        schema_argument_fit = _schema_argument_fit(intent_tokens, capability)
        success_history = min(1.0, self.history.successes.get(capability.name, 0) / 5)
        failure_history_penalty = min(1.0, self.history.failures.get(capability.name, 0) / 5)
        risk_penalty = {
            "tier_0": 0.0,
            "tier_1": 0.2,
            "tier_2": 0.5,
            "tier_3": 0.8,
        }.get(str(capability.risk_tier), 0.5)
        side_effect_penalty = 0.0 if capability.side_effect_classification == "none" else 0.2
        recency = 1 / (1 + self.history.last_used_rank.get(capability.name, 10))
        availability_penalty = 1.0 if capability.name in self.availability.unavailable else 0.0
        return {
            "semantic_similarity": semantic_similarity,
            "schema_argument_fit": schema_argument_fit,
            "success_history": success_history,
            "failure_history_penalty": failure_history_penalty,
            "risk_penalty": risk_penalty,
            "side_effect_penalty": side_effect_penalty,
            "platform_availability": 1.0,
            "availability_penalty": availability_penalty,
            "recency": recency,
        }


def _schema_argument_fit(intent_tokens: set[str], capability: CapabilityDefinition) -> float:
    properties = capability.input_schema.get("properties", {})
    if not isinstance(properties, dict) or not properties:
        return 0.5
    arg_tokens = set(properties)
    return len(intent_tokens & arg_tokens) / max(1, len(arg_tokens))


def _weighted_score(signals: dict[str, float]) -> float:
    positive = (
        signals["semantic_similarity"] * 2.5
        + signals["schema_argument_fit"]
        + signals["success_history"] * 0.5
        + signals["platform_availability"]
        + signals["recency"] * 0.2
    )
    negative = (
        signals["failure_history_penalty"]
        + signals["risk_penalty"]
        + signals["side_effect_penalty"]
        + signals["availability_penalty"]
    )
    return 1 / (1 + math.exp(-(positive - negative)))


def _rejection_reason(candidate: CapabilityCandidate) -> str:
    signals = candidate.ranking_signals
    if signals.get("availability_penalty", 0.0) > 0:
        return "unavailable_adapter"
    if signals.get("risk_penalty", 0.0) >= 0.5:
        return "higher_risk"
    if signals.get("side_effect_penalty", 0.0) > 0:
        return "side_effect_penalty"
    return "lower_rank"
