"""
Token usage tracking, Context Cache Hit Rate analysis, and operational cost estimation.
"""
import logging
from dataclasses import dataclass
from typing import Optional, Any
from opentelemetry.trace import Span

from travel_concierge.config import settings

logger = logging.getLogger("travel_concierge.cost_tracker")


@dataclass
class TokenUsageMetrics:
    """Calculated token telemetry and financial metrics."""
    prompt_tokens: int
    cached_tokens: int
    uncached_prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    cache_hit_rate: float
    cost_usd: float

    @property
    def cost_savings_pct(self) -> float:
        """Percentage of token costs saved due to cache discount (75% discount on cached tokens)."""
        return round(self.cache_hit_rate * 75.0, 1)

    def to_dict(self) -> dict:
        return {
            "prompt_tokens": self.prompt_tokens,
            "cached_tokens": self.cached_tokens,
            "uncached_prompt_tokens": self.uncached_prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "total_tokens": self.total_tokens,
            "cache_hit_rate": round(self.cache_hit_rate, 4),
            "cost_savings_pct": self.cost_savings_pct,
            "cost_usd": round(self.cost_usd, 6),
        }


def calculate_token_cost(
    prompt_tokens: int,
    cached_tokens: int,
    completion_tokens: int,
    input_price_per_1m: Optional[float] = None,
    cached_input_price_per_1m: Optional[float] = None,
    output_price_per_1m: Optional[float] = None,
) -> TokenUsageMetrics:
    """
    Computes cache hit rate and monetary cost based on tiered Gemini pricing.
    """
    input_price = input_price_per_1m if input_price_per_1m is not None else settings.pricing.input_price_per_1m
    cached_price = (
        cached_input_price_per_1m
        if cached_input_price_per_1m is not None
        else settings.pricing.cached_input_price_per_1m
    )
    output_price = output_price_per_1m if output_price_per_1m is not None else settings.pricing.output_price_per_1m

    # Non-cached prompt tokens = Total Prompt Tokens - Cached Tokens
    uncached_prompt = max(0, prompt_tokens - cached_tokens)
    total = prompt_tokens + completion_tokens

    # Context Cache Hit Rate: cachedContentTokenCount / promptTokenCount
    cache_hit_rate = (cached_tokens / prompt_tokens) if prompt_tokens > 0 else 0.0

    # Operational cost calculation with explicit cache discount
    cost = (
        ((uncached_prompt / 1_000_000) * input_price)
        + ((cached_tokens / 1_000_000) * cached_price)
        + ((completion_tokens / 1_000_000) * output_price)
    )

    return TokenUsageMetrics(
        prompt_tokens=prompt_tokens,
        cached_tokens=cached_tokens,
        uncached_prompt_tokens=uncached_prompt,
        completion_tokens=completion_tokens,
        total_tokens=total,
        cache_hit_rate=cache_hit_rate,
        cost_usd=cost,
    )


def extract_usage_from_response(response: Any) -> Optional[dict]:
    """Helper to extract token usage counts from diverse response formats (SDK, ADK, dict)."""
    if response is None:
        return None

    usage = getattr(response, "usage_metadata", None)
    if usage is None and isinstance(response, dict):
        usage = response.get("usage_metadata") or response.get("usage")

    if not usage:
        return None

    if isinstance(usage, dict):
        prompt_tokens = usage.get("prompt_token_count", usage.get("prompt_tokens", 0))
        cached_tokens = usage.get("cached_content_token_count", usage.get("cached_tokens", 0))
        completion_tokens = usage.get("candidates_token_count", usage.get("completion_tokens", 0))
        total_tokens = usage.get("total_token_count", usage.get("total_tokens", prompt_tokens + completion_tokens))
    else:
        prompt_tokens = getattr(usage, "prompt_token_count", getattr(usage, "prompt_tokens", 0))
        cached_tokens = getattr(usage, "cached_content_token_count", getattr(usage, "cached_tokens", 0))
        completion_tokens = getattr(usage, "candidates_token_count", getattr(usage, "completion_tokens", 0))
        total_tokens = getattr(usage, "total_token_count", getattr(usage, "total_tokens", prompt_tokens + completion_tokens))

    return {
        "prompt_tokens": int(prompt_tokens or 0),
        "cached_tokens": int(cached_tokens or 0),
        "completion_tokens": int(completion_tokens or 0),
        "total_tokens": int(total_tokens or 0),
    }


def track_llm_telemetry(
    response: Any,
    span: Optional[Span] = None,
    agent_name: str = "agent",
    prompt_text: Optional[str] = None,
) -> Optional[TokenUsageMetrics]:
    """
    Extracts usage from response, calculates costs, updates OpenTelemetry span attributes,
    records prompts and completions for forensic trace analysis, and logs verbose context
    management decisions for educational observability.
    """
    raw_usage = extract_usage_from_response(response)
    if not raw_usage:
        return None

    metrics = calculate_token_cost(
        prompt_tokens=raw_usage["prompt_tokens"],
        cached_tokens=raw_usage["cached_tokens"],
        completion_tokens=raw_usage["completion_tokens"],
    )

    resp_str = str(response)

    if span and span.is_recording():
        span.set_attribute(f"llm.{agent_name}.prompt_tokens", metrics.prompt_tokens)
        span.set_attribute(f"llm.{agent_name}.cached_tokens", metrics.cached_tokens)
        span.set_attribute(f"llm.{agent_name}.completion_tokens", metrics.completion_tokens)
        span.set_attribute(f"llm.{agent_name}.total_tokens", metrics.total_tokens)
        span.set_attribute(f"llm.{agent_name}.cache_hit_rate", metrics.cache_hit_rate)
        span.set_attribute(f"llm.{agent_name}.cost_usd", metrics.cost_usd)
        if prompt_text:
            span.set_attribute(f"gen_ai.{agent_name}.prompt", str(prompt_text)[:2048])
        span.set_attribute(f"gen_ai.{agent_name}.completion", resp_str[:2048])

    # Verbose context management explanation for educational telemetry
    if metrics.cached_tokens > 0:
        logger.info(
            f"[{agent_name} Context Management] Explicit Context Caching Active. "
            f"Preserved {metrics.cached_tokens}/{metrics.prompt_tokens} tokens in Vertex AI cache "
            f"(Hit Rate: {metrics.cache_hit_rate:.1%}, Cost Savings: {metrics.cost_savings_pct:.1f}%). "
            f"Technique: Deterministic Prefix Alignment ensures instructions and schemas are reused without cache invalidation."
        )

    if metrics.cache_hit_rate < 0.50 and metrics.prompt_tokens > 4096:
        logger.warning(
            f"[{agent_name}] Cache hit rate low ({metrics.cache_hit_rate:.1%}). "
            f"Inspect dynamic context placement or prefix drift."
        )

    logger.info(
        f"[{agent_name} Telemetry] Prompt: {metrics.prompt_tokens} (Cached: {metrics.cached_tokens}) | "
        f"Hit Rate: {metrics.cache_hit_rate:.2%} | Cost: ${metrics.cost_usd:.6f}"
    )

    return metrics
