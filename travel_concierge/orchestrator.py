"""
Pipeline Orchestrator and CLI runner for the Travel Concierge Multi-Agent System.
"""
import argparse
import json
import logging
import sys

from travel_concierge.telemetry.tracer import init_tracer
from travel_concierge.agents.root_agent import TravelConciergeRootAgent

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("travel_concierge.orchestrator")


def run_pipeline(destination: str = "Tokyo Shinjuku", dining_query: str = "vegan dinner options"):
    """Executes the full multi-agent travel concierge pipeline."""
    init_tracer("travel_concierge_cli")
    logger.info("Initializing Travel Concierge Multi-Agent Orchestrator...")

    root_agent = TravelConciergeRootAgent()

    valid_token_claims = {
        "sub": "user:alice@example.com",
        "groups": ["MCPUSERS", "TRAVELERS"],
        "scope": "https://mcp-server.zomato.com/scopes/restaurants.read",
    }

    result = root_agent.plan_trip(
        destination=destination,
        dining_query=dining_query,
        context_id=f"ctx-{destination.lower().replace(' ', '-')}-2026",
        token_claims=valid_token_claims,
        auto_confirm_booking=True,
    )

    print("\n" + "=" * 60)
    print("           TRAVEL CONCIERGE TRIP SUMMARY")
    print("=" * 60)
    print(f"Context ID:       {result['context_id']}")
    print(f"Destination:      {result['destination']}")
    print(f"Hotel Task ID:    {result['hotel_booking']['task_id']}")
    print(f"Hotel Response:   {result['hotel_booking']['response']}")
    print(f"Dining Response:  {result['restaurant_recommendations']['response']}")
    print(f"Verification:     {result['verification']['state']}")
    print("-" * 60)
    print("               TELEMETRY & PRICING")
    print("-" * 60)
    telemetry = result["telemetry"]
    print(f"Total Tokens:     {telemetry['total_tokens']}")
    print(f"Prompt Tokens:    {telemetry['prompt_tokens']} (Cached: {telemetry['cached_tokens']})")
    print(f"Cache Hit Rate:   {telemetry['cache_hit_rate'] * 100:.2f}%")
    print(f"Total Cost (USD): ${telemetry['cost_usd']:.6f}")
    print("=" * 60 + "\n")

    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Travel Concierge Multi-Agent Runner")
    parser.add_argument("--destination", type=str, default="Tokyo Shinjuku", help="Trip destination")
    parser.add_argument("--query", type=str, default="vegan dinner options", help="Dining query")
    args = parser.parse_args()

    run_pipeline(destination=args.destination, dining_query=args.query)
