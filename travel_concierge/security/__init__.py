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
from travel_concierge.security.model_armor import (
    ModelArmor,
    ModelArmorViolationError,
    InspectionResult,
    guard_prompt,
    default_model_armor,
)

from travel_concierge.security.gateway_policy import (
    AgentGatewayPolicy,
    GatewayPolicyMiddleware,
    GatewayPolicyViolationError,
    default_gateway_policy,
)

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
    "ModelArmor",
    "ModelArmorViolationError",
    "InspectionResult",
    "guard_prompt",
    "default_model_armor",
    "AgentGatewayPolicy",
    "GatewayPolicyMiddleware",
    "GatewayPolicyViolationError",
    "default_gateway_policy",
]
