"""
Pytest configuration and shared fixtures.
"""
import pytest
from typing import Dict, Any

from travel_concierge.config import Settings, PricingConfig, CircuitBreakerConfig
from travel_concierge.cache.context_cache import ExplicitContextCacheManager
from travel_concierge.security.circuit_breaker import MCPCircuitBreaker


@pytest.fixture
def mock_settings() -> Settings:
    return Settings(
        project_id="test-gcp-project",
        location="us-central1",
        model_name="gemini-2.5-flash",
        pricing=PricingConfig(
            input_price_per_1m=0.30,
            cached_input_price_per_1m=0.075,
            output_price_per_1m=2.50,
        ),
        circuit_breaker=CircuitBreakerConfig(
            failure_threshold=3,
            recovery_timeout=0.1,  # Fast for testing
            execution_timeout=0.5,
        ),
    )


@pytest.fixture
def valid_token_claims() -> Dict[str, Any]:
    return {
        "sub": "user:test_user@example.com",
        "groups": ["MCPUSERS", "TRAVELERS"],
        "scope": "https://mcp-server.zomato.com/scopes/restaurants.read",
    }


@pytest.fixture
def unauthorized_group_token_claims() -> Dict[str, Any]:
    return {
        "sub": "user:unauthorized@example.com",
        "groups": ["GUEST"],
        "scope": "https://mcp-server.zomato.com/scopes/restaurants.read",
    }


@pytest.fixture
def unauthorized_scope_token_claims() -> Dict[str, Any]:
    return {
        "sub": "user:limited@example.com",
        "groups": ["MCPUSERS"],
        "scope": "https://other-service.com/read",
    }


@pytest.fixture
def fast_circuit_breaker() -> MCPCircuitBreaker:
    return MCPCircuitBreaker(
        name="test_circuit_breaker",
        failure_threshold=3,
        recovery_timeout=0.1,
        execution_timeout=0.2,
    )


@pytest.fixture
def mock_cache_manager() -> ExplicitContextCacheManager:
    return ExplicitContextCacheManager(project_id="test-gcp-project", use_mock=True)
