"""
Security and resilience guardrails package.
"""
from travel_concierge.security.circuit_breaker import (
    MCPCircuitBreaker,
    CircuitBreakerOpenException,
    CircuitBreakerState,
)
from travel_concierge.security.auth_guardrails import (
    require_mcp_group_membership,
    require_oauth_scope,
    validate_agent_gateway_headers,
    build_gateway_headers,
)
from travel_concierge.security.ssrf_validator import is_safe_webhook_url, SSRFValidationError

__all__ = [
    "MCPCircuitBreaker",
    "CircuitBreakerOpenException",
    "CircuitBreakerState",
    "require_mcp_group_membership",
    "require_oauth_scope",
    "validate_agent_gateway_headers",
    "build_gateway_headers",
    "is_safe_webhook_url",
    "SSRFValidationError",
]
