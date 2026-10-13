"""
Model Escalation Engine.
Provides deterministic complexity evaluation to escalate agents from
gemini-3.5-flash to gemini-3.5 when reasoning demands require larger models.
All escalation decisions are auditable and exported to OpenTelemetry traces.
"""
import logging
from dataclasses import dataclass
from typing import Optional, Dict, Any, List
from opentelemetry.trace import Span

from travel_concierge.config import settings
from travel_concierge.telemetry.tracer import get_tracer

logger = logging.getLogger("travel_concierge.model_escalator")
tracer = get_tracer("travel_concierge.model_escalator")


@dataclass
class EscalationDecision:
    escalated: bool
    initial_model: str
    active_model: str
    reason: Optional[str] = None
    complexity_score: float = 0.0

    @property
    def score(self) -> float:
        return self.complexity_score

    @property
    def rationale(self) -> Optional[str]:
        return self.reason

    def to_dict(self) -> Dict[str, Any]:
        return {
            "escalated": self.escalated,
            "initial_model": self.initial_model,
            "active_model": self.active_model,
            "reason": self.reason,
            "complexity_score": round(self.complexity_score, 2),
        }


class ModelEscalationManager:
    """
    Evaluates request complexity, constraint density, and ambiguity to determine
    if an agent should escalate from the fast/efficient gemini-3.5-flash model
    to the deeper reasoning gemini-3.5 model.
    """

    COMPLEXITY_TRIGGERS = [
        # Multiple simultaneous dietary/allergy constraints
        (r"\b(?:vegan|plant-based)\b.*\b(?:halal|kosher)\b", 3.0, "Compound dietary overlap (Vegan + Halal/Kosher)"),
        (r"\b(?:gluten-free|celiac)\b.*\b(?:nut\s+allergy|shellfish\s+allergy)\b", 3.5, "Severe dual allergy cross-contact risks"),
        # Cross-regional international normalization conflict
        (r"\b(?:compare|cross-reference|normalize)\b.*\b(?:tokyo|nyc|uk)\b", 2.5, "Multi-jurisdiction hygiene score normalization"),
        # Multi-turn itinerary contradiction or heavy schedule constraints
        (r"\b(?:cancel|change|rebook|replace|instead\s+of|switch)\b", 2.0, "Multi-turn state modification and reservation mutation"),
        # Budget / cost optimization under strict bounds
        (r"\b(?:budget\s+under|cheap|cost-sensitive|lowest\s+price)\b", 1.5, "Multi-variable budget optimization"),
    ]

    def __init__(
        self,
        base_model: Optional[str] = None,
        escalated_model: Optional[str] = None,
        threshold: float = 2.0,
    ):
        self.base_model = base_model or getattr(settings, "base_model_name", "gemini-3.5-flash")
        self.escalated_model = escalated_model or getattr(settings, "escalated_model_name", "gemini-3.5")
        self.threshold = threshold

    def evaluate_request(
        self,
        query: str,
        context_history_turns: int = 0,
        span: Optional[Span] = None,
        agent_name: str = "agent",
    ) -> EscalationDecision:
        """
        Assesses prompt complexity score. If score >= threshold, escalates to gemini-3.5.
        Traces and logs the exact escalation rationale.
        """
        import re

        total_score = 0.0
        reasons: List[str] = []

        query_lower = query.lower()

        for pattern, weight, reason in self.COMPLEXITY_TRIGGERS:
            if re.search(pattern, query_lower, re.IGNORECASE):
                total_score += weight
                reasons.append(reason)

        # Longer multi-turn conversations also increment complexity score
        if context_history_turns > 2:
            total_score += 1.5
            reasons.append(f"Extended multi-turn depth ({context_history_turns} turns)")

        should_escalate = total_score >= self.threshold
        active_model = self.escalated_model if should_escalate else self.base_model
        combined_reason = "; ".join(reasons) if reasons else ("Baseline complexity" if not should_escalate else "High complexity")

        decision = EscalationDecision(
            escalated=should_escalate,
            initial_model=self.base_model,
            active_model=active_model,
            reason=combined_reason if should_escalate else "Prompt within baseline capabilities",
            complexity_score=total_score,
        )

        if span and span.is_recording():
            span.set_attribute(f"llm.{agent_name}.escalated", decision.escalated)
            span.set_attribute(f"llm.{agent_name}.initial_model", decision.initial_model)
            span.set_attribute(f"llm.{agent_name}.active_model", decision.active_model)
            span.set_attribute(f"llm.{agent_name}.escalation_reason", decision.reason or "")
            span.set_attribute(f"llm.{agent_name}.complexity_score", decision.complexity_score)

        if should_escalate:
            logger.info(
                f"[{agent_name} Model Escalation] ESCALATED from {self.base_model} -> {self.escalated_model}. "
                f"Score: {total_score:.1f} (Threshold: {self.threshold}). Rationale: {combined_reason}"
            )
        else:
            logger.info(
                f"[{agent_name} Model Selection] Retained {self.base_model} (Score: {total_score:.1f} < {self.threshold})."
            )

        return decision


# Default global escalation manager instance
default_escalator = ModelEscalationManager()


def assess_complexity(query: str, context_history_turns: int = 0) -> EscalationDecision:
    """Helper function to assess prompt complexity using default_escalator."""
    return default_escalator.evaluate_request(query=query, context_history_turns=context_history_turns)
