"""
Shared instructions, generation configs, and caching initialization for agents.
"""
import logging
from typing import Optional, Any

from google.genai import types

from travel_concierge.config import settings
from travel_concierge.cache.context_cache import ExplicitContextCacheManager

logger = logging.getLogger("travel_concierge.agents.base")

SHARED_SYSTEM_INSTRUCTION = """
You are an enterprise travel dining and hotel concierge agent.
Operational Guidelines:
1. Load validation workflows dynamically from GCPSkillRegistry.
2. Search available registry skills (like 'dietary_advisor') to filter dining options.
3. If tool execution returns a 403 Forbidden error or a 'degraded_fallback' status, clearly explain the access limitation or present cached default options.
4. Pass reference task IDs accurately between hotel and restaurant booking agents.

Formatting & Output Efficiency Guardrails:
- Be extremely concise. Avoid preambles, conversational filler, conversational greetings, or concluding remarks.
- Deliver requested structured information immediately.
"""


def get_generation_config(
    max_output_tokens: Optional[int] = None,
    stop_sequences: Optional[list] = None,
    response_mime_type: Optional[str] = None,
    thinking_budget: Optional[int] = None,
    thinking_level: Optional[str] = None,
    cached_content: Optional[str] = None,
) -> types.GenerateContentConfig:
    """Creates a standardized GenerateContentConfig applying enterprise guardrails."""
    t_budget = thinking_budget if thinking_budget is not None else settings.guardrails.thinking_budget
    if t_budget is not None and t_budget > 0:
        thinking_cfg = types.ThinkingConfig(thinking_budget=t_budget)
    elif thinking_level or settings.guardrails.thinking_level:
        thinking_cfg = types.ThinkingConfig(thinking_level=thinking_level or settings.guardrails.thinking_level)
    else:
        thinking_cfg = None

    kwargs = {
        "max_output_tokens": max_output_tokens or settings.guardrails.max_output_tokens,
        "stop_sequences": stop_sequences or settings.guardrails.stop_sequences,
        "response_mime_type": response_mime_type or settings.guardrails.response_mime_type,
    }
    if thinking_cfg:
        kwargs["thinking_config"] = thinking_cfg
    if cached_content:
        kwargs["cached_content"] = cached_content

    return types.GenerateContentConfig(**kwargs)


def get_cached_content(
    cache_manager: Optional[ExplicitContextCacheManager] = None,
    model: Optional[str] = None,
    system_instruction: str = SHARED_SYSTEM_INSTRUCTION,
    ttl_minutes: int = 60,
    display_name: str = "travel_concierge_base_cache",
) -> Any:
    """Creates or returns an explicit context cache object."""
    cm = cache_manager or ExplicitContextCacheManager()
    return cm.create_agent_context_cache(
        model=model or settings.model_name,
        system_instruction=system_instruction,
        ttl_minutes=ttl_minutes,
        display_name=display_name,
    )
