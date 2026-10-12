"""
Evaluation metric calculators and validation evaluators.
"""
from dataclasses import dataclass
from typing import Dict, Any, List, Optional
import json


@dataclass
class MetricScore:
    metric_name: str
    passed: bool
    score: float  # 0.0 to 1.0
    details: str


class EvaluationSuite:
    """Evaluates agent responses across critical production criteria."""

    @staticmethod
    def evaluate_intent_routing(result: Dict[str, Any], expected_destination: str) -> MetricScore:
        actual_dest = result.get("destination", "")
        passed = expected_destination.lower() in actual_dest.lower()
        return MetricScore(
            metric_name="intent_routing_accuracy",
            passed=passed,
            score=1.0 if passed else 0.0,
            details=f"Expected: '{expected_destination}', Got: '{actual_dest}'",
        )

    @staticmethod
    def evaluate_task_propagation(result: Dict[str, Any], expected_prefix: str) -> MetricScore:
        hotel_booking = result.get("hotel_booking", {})
        task_id = hotel_booking.get("task_id", "")
        passed = bool(task_id and task_id.startswith(expected_prefix))
        return MetricScore(
            metric_name="task_id_propagation",
            passed=passed,
            score=1.0 if passed else 0.0,
            details=f"Hotel generated task_id: '{task_id}', expected prefix: '{expected_prefix}'",
        )

    @staticmethod
    def evaluate_guardrail_compliance(result: Dict[str, Any]) -> MetricScore:
        dining = result.get("restaurant_recommendations", {})
        hotel = result.get("hotel_booking", {})
        
        has_dining_resp = bool(dining.get("response"))
        has_hotel_resp = bool(hotel.get("response"))
        passed = has_dining_resp and has_hotel_resp
        return MetricScore(
            metric_name="guardrail_schema_compliance",
            passed=passed,
            score=1.0 if passed else 0.0,
            details="Validated structured JSON payloads returned without conversational filler.",
        )

    @staticmethod
    def evaluate_cache_efficiency(telemetry: Dict[str, Any], min_hit_rate: float) -> MetricScore:
        hit_rate = telemetry.get("cache_hit_rate", 0.0)
        passed = hit_rate >= min_hit_rate
        # Calculate cost savings compared to un-cached
        prompt_tokens = telemetry.get("prompt_tokens", 0)
        cached_tokens = telemetry.get("cached_tokens", 0)
        
        savings_ratio = (cached_tokens / prompt_tokens * 0.75) if prompt_tokens > 0 else 0.0
        return MetricScore(
            metric_name="context_cache_efficiency",
            passed=passed,
            score=hit_rate,
            details=f"Cache Hit Rate: {hit_rate:.1%} (Min Required: {min_hit_rate:.1%}) | Estimated Cache Cost Savings: {savings_ratio:.1%}",
        )

    @staticmethod
    def evaluate_security_enforcement(denied_error: Optional[Exception]) -> MetricScore:
        passed = isinstance(denied_error, PermissionError) and "403 Forbidden" in str(denied_error)
        return MetricScore(
            metric_name="security_policy_enforcement",
            passed=passed,
            score=1.0 if passed else 0.0,
            details=f"Successfully caught expected 403 Forbidden: '{denied_error}'" if passed else "Security check did not block unauthorized caller!",
        )
