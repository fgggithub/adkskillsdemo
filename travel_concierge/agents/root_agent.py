"""
Root Orchestrator Agent: Travel Concierge.
Coordinates subagents (hotel, restaurant, verification), context caching, and OpenTelemetry tracing.
"""
import logging
import uuid
from typing import Dict, Any, Optional, List

from google.adk.agents import Agent

from travel_concierge.config import settings
from travel_concierge.telemetry.tracer import get_tracer, inject_trace_context
from travel_concierge.telemetry.cost_tracker import calculate_token_cost, TokenUsageMetrics
from travel_concierge.agents.base import SHARED_SYSTEM_INSTRUCTION, get_generation_config, get_cached_content
from travel_concierge.agents.restaurant_agent import create_restaurant_subagent, RestaurantAgentWrapper
from travel_concierge.agents.hotel_agent import create_hotel_subagent, HotelAgentWrapper
from travel_concierge.agents.verification_agent import create_verification_subagent, VerificationAgentWrapper
from travel_concierge.tools.skill_registry import get_skill_registry_toolset

logger = logging.getLogger("travel_concierge.root_agent")
tracer = get_tracer("travel_concierge.root_agent")


def create_travel_concierge_root_agent(
    cached_content_name: Optional[str] = None,
    hotel_subagent: Optional[Any] = None,
    restaurant_subagent: Optional[Any] = None,
    skill_toolset: Optional[Any] = None,
) -> Agent:
    """Factory creating the primary Travel Concierge Orchestrator Agent."""
    tools = [skill_toolset or get_skill_registry_toolset()]
    sub_agents = [
        hotel_subagent or create_hotel_subagent(),
        restaurant_subagent or create_restaurant_subagent(cached_content_name=cached_content_name),
    ]

    return Agent(
        name="travel_concierge_orchestrator",
        model=settings.model_name,
        instruction=SHARED_SYSTEM_INSTRUCTION,
        tools=tools,
        sub_agents=sub_agents,
        generate_content_config=get_generation_config(cached_content=cached_content_name),
    )


class TravelConciergeRootAgent:
    """
    Production Root Travel Concierge Orchestrator.
    Manages end-to-end trip planning workflows across hotel accommodations,
    restaurant dining, and human-in-the-loop task verification.
    """

    def __init__(
        self,
        cached_content_name: Optional[str] = None,
        hotel_wrapper: Optional[HotelAgentWrapper] = None,
        restaurant_wrapper: Optional[RestaurantAgentWrapper] = None,
        verification_wrapper: Optional[VerificationAgentWrapper] = None,
    ):
        if cached_content_name is None:
            cache_obj = get_cached_content()
            self.cached_content_name = getattr(cache_obj, "name", "projects/local/locations/us-central1/cachedContents/default")
        else:
            self.cached_content_name = cached_content_name

        self.hotel_agent = hotel_wrapper or HotelAgentWrapper()
        self.restaurant_agent = restaurant_wrapper or RestaurantAgentWrapper(
            cached_content_name=self.cached_content_name
        )
        self.verification_agent = verification_wrapper or VerificationAgentWrapper()
        self.adk_agent = create_travel_concierge_root_agent(cached_content_name=self.cached_content_name)

    def plan_trip(
        self,
        destination: str,
        dining_query: str = "vegan dinner options near the hotel",
        context_id: Optional[str] = None,
        token_claims: Optional[Dict[str, Any]] = None,
        auto_confirm_booking: bool = True,
    ) -> Dict[str, Any]:
        """
        Orchestrates full travel itinerary planning:
        1. Reserves hotel hold via Hotel Sub-Agent -> generates reference task ID.
        2. Searches dining recommendations via Restaurant Sub-Agent passing reference task ID.
        3. Executes verification & payment confirmation via Task-based Verification Sub-Agent.
        4. Calculates end-to-end token consumption, cache hit rate, and operational cost.
        """
        trip_context_id = context_id or f"ctx-{destination.lower().replace(' ', '-')}-{uuid.uuid4().hex[:6]}"

        with tracer.start_as_current_span("orchestrate_trip_planning") as root_span:
            root_span.set_attribute("a2a.context_id", trip_context_id)
            root_span.set_attribute("a2a.destination", destination)

            logger.info(f"=== Starting Travel Concierge Pipeline [Context: {trip_context_id}] ===")

            # Step 1: Delegate to Hotel Sub-Agent
            hotel_result = self.hotel_agent.search_and_hold_hotel(
                context_id=trip_context_id,
                location=destination,
            )
            hotel_task_id = hotel_result.get("task_id", "task-hotel-default")
            logger.info(f"[Step 1 Complete] Hotel Held. Reference Task ID: {hotel_task_id}")

            # Step 2: Delegate to Restaurant Sub-Agent with Reference Task ID
            restaurant_result = self.restaurant_agent.find_dining_options(
                context_id=trip_context_id,
                query=f"{dining_query} near {destination}",
                reference_task_ids=[hotel_task_id],
                token_claims=token_claims,
            )
            logger.info(f"[Step 2 Complete] Dining options retrieved.")

            # Step 3: Final Verification & Confirmation (HITL Streaming Task)
            verification_result = self.verification_agent.run_verification_task(
                context_id=trip_context_id,
                reference_task_ids=[hotel_task_id],
                user_auto_confirm=auto_confirm_booking,
            )
            logger.info(f"[Step 3 Complete] Verification State: {verification_result.get('state')}")

            # Step 4: Aggregate Telemetry & Pricing
            metrics_list = [
                hotel_result.get("metrics"),
                restaurant_result.get("metrics"),
                verification_result.get("metrics"),
            ]

            total_prompt_tokens = sum(m["prompt_tokens"] for m in metrics_list if m)
            total_cached_tokens = sum(m["cached_tokens"] for m in metrics_list if m)
            total_completion_tokens = sum(m["completion_tokens"] for m in metrics_list if m)

            aggregate_metrics = calculate_token_cost(
                prompt_tokens=total_prompt_tokens,
                cached_tokens=total_cached_tokens,
                completion_tokens=total_completion_tokens,
            )

            root_span.set_attribute("llm.pipeline.total_tokens", aggregate_metrics.total_tokens)
            root_span.set_attribute("llm.pipeline.cached_tokens", aggregate_metrics.cached_tokens)
            root_span.set_attribute("llm.pipeline.cache_hit_rate", aggregate_metrics.cache_hit_rate)
            root_span.set_attribute("llm.pipeline.cost_usd", aggregate_metrics.cost_usd)

            logger.info(f"=== Travel Concierge Pipeline Completed ===")
            logger.info(f"Total Tokens: {aggregate_metrics.total_tokens} | Cached: {aggregate_metrics.cached_tokens} ({aggregate_metrics.cache_hit_rate:.1%})")
            logger.info(f"Pipeline Estimated Cost: ${aggregate_metrics.cost_usd:.6f}")

            return {
                "context_id": trip_context_id,
                "destination": destination,
                "hotel_booking": hotel_result,
                "restaurant_recommendations": restaurant_result,
                "verification": verification_result,
                "telemetry": aggregate_metrics.to_dict(),
            }
