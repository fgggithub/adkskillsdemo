"""
Zomato MCP Toolset initialization and protected execution wrappers.
"""
import logging
from typing import Dict, Any, Optional
from dataclasses import dataclass

from google.adk.tools import McpToolset
from google.adk.tools.mcp_tool.mcp_session_manager import StreamableHTTPConnectionParams

from travel_concierge.config import settings
from travel_concierge.security.circuit_breaker import MCPCircuitBreaker
from travel_concierge.security.auth_guardrails import (
    require_mcp_group_membership,
    require_oauth_scope,
)

logger = logging.getLogger("travel_concierge.mcp_toolset")


@dataclass
class GcpAuthProviderScheme:
    """GCP Identity / OIDC Auth Scheme for MCP HTTP connections."""
    audience: str


# Global circuit breaker instance for Zomato calls
zomato_circuit_breaker = MCPCircuitBreaker(
    name="zomato_mcp_circuit_breaker",
    failure_threshold=settings.circuit_breaker.failure_threshold,
    recovery_timeout=settings.circuit_breaker.recovery_timeout,
    execution_timeout=settings.circuit_breaker.execution_timeout,
)


@require_mcp_group_membership("MCPUSERS")
@require_oauth_scope("https://mcp-server.zomato.com/scopes/restaurants.read")
@zomato_circuit_breaker
def execute_zomato_search(
    token_claims: dict,
    query: str,
    cuisine: Optional[str] = None,
    dietary_restriction: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Simulated or direct call to Zomato MCP search endpoint, protected by IAM, OAuth,
    and Circuit Breaker resilience.
    """
    logger.info(f"Executing Zomato search for query='{query}', cuisine='{cuisine}', dietary='{dietary_restriction}'")

    results = [
        f"1. Tokyo Vegan Izakaya - Query Match: {query} (Rating: 4.8, Vegan friendly)",
        f"2. Shinjuku Plant Craft Ramen - Query Match: {query} (Rating: 4.6, 100% Plant-based)",
        f"3. Kyoto Green Tea & Soba Kitchen - Query Match: {query} (Rating: 4.7, Organic)",
    ]

    return {
        "status": "success",
        "query": query,
        "cuisine": cuisine,
        "dietary_restriction": dietary_restriction,
        "results": results,
    }


def get_zomato_mcp_toolset(url: Optional[str] = None) -> McpToolset:
    """
    Factory creating a configured McpToolset instance with GCP Identity Token authentication.
    """
    endpoint_url = url or settings.endpoints.zomato_mcp_url
    return McpToolset(
        connection_params=StreamableHTTPConnectionParams(
            url=endpoint_url,
            headers={"Authorization": f"Bearer mock-gcp-token-for-{endpoint_url}"},
        ),
        tool_filter=[
            "search_restaurants",
            "get_restaurant_details",
            "get_restaurant_reviews",
            "search_by_cuisine",
        ],
    )
