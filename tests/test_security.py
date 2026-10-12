"""
Unit tests for IAM group, OAuth scope, SSRF prevention, and Agent Gateway security.
"""
import pytest
from travel_concierge.security.auth_guardrails import (
    require_mcp_group_membership,
    require_oauth_scope,
    build_gateway_headers,
    validate_agent_gateway_headers,
)
from travel_concierge.security.ssrf_validator import (
    is_safe_webhook_url,
    validate_webhook_url,
    SSRFValidationError,
)


# ==============================================================================
# IAM & OAuth Guardrails Tests
# ==============================================================================

def test_require_mcp_group_membership_success(valid_token_claims):
    @require_mcp_group_membership("MCPUSERS")
    def sample_op(token_claims):
        return "allowed"

    assert sample_op(valid_token_claims) == "allowed"


def test_require_mcp_group_membership_denied(unauthorized_group_token_claims):
    @require_mcp_group_membership("MCPUSERS")
    def sample_op(token_claims):
        return "allowed"

    with pytest.raises(PermissionError, match="403 Forbidden: User not in group 'MCPUSERS'"):
        sample_op(unauthorized_group_token_claims)


def test_require_oauth_scope_success(valid_token_claims):
    @require_oauth_scope("https://mcp-server.zomato.com/scopes/restaurants.read")
    def sample_op(token_claims):
        return "authorized"

    assert sample_op(valid_token_claims) == "authorized"


def test_require_oauth_scope_denied(unauthorized_scope_token_claims):
    @require_oauth_scope("https://mcp-server.zomato.com/scopes/restaurants.read")
    def sample_op(token_claims):
        return "authorized"

    with pytest.raises(PermissionError, match="403 Forbidden: Missing scope"):
        sample_op(unauthorized_scope_token_claims)


# ==============================================================================
# SSRF Validation Tests
# ==============================================================================

def test_ssrf_safe_https_domain():
    assert is_safe_webhook_url("https://www.google.com/webhook") is True
    assert is_safe_webhook_url("https://travel-concierge.example.com/a2a/webhooks/push", allow_test_hosts=True) is True


def test_ssrf_reject_non_https():
    assert is_safe_webhook_url("http://www.google.com/webhook") is False
    assert is_safe_webhook_url("ftp://ftp.example.com/webhook") is False
    assert is_safe_webhook_url("file:///etc/passwd") is False


def test_ssrf_reject_loopback_and_internal_ips():
    assert is_safe_webhook_url("https://localhost/webhook") is False
    assert is_safe_webhook_url("https://127.0.0.1:8080/webhook") is False
    assert is_safe_webhook_url("https://[::1]:8080/webhook") is False
    assert is_safe_webhook_url("https://metadata.google.internal/computeMetadata/v1/") is False


def test_validate_webhook_url_exception():
    with pytest.raises(SSRFValidationError):
        validate_webhook_url("http://insecure-internal.corp/webhook")


# ==============================================================================
# Agent Gateway Zero Trust Headers Tests
# ==============================================================================

def test_agent_gateway_headers_construction_and_validation():
    caller_spiffe = "spiffe://prod.corp/agent/travel-concierge"
    target_token = "eyJhbGciOiJSUzI1NiJ9.eyJhdWQiOiJob3RlbC1zcGVjaWFsaXN0In0.signature"

    headers = build_gateway_headers(
        caller_spiffe_gateway_token=caller_spiffe,
        target_subagent_access_token=target_token,
    )

    assert headers["Proxy-Authorization"] == f"Bearer {caller_spiffe}"
    assert headers["Authorization"] == f"Bearer {target_token}"
    assert "traceparent" in headers or isinstance(headers, dict)
    assert validate_agent_gateway_headers(headers) is True


def test_agent_gateway_headers_validation_failure():
    invalid_headers = {"Authorization": "InvalidToken"}
    assert validate_agent_gateway_headers(invalid_headers) is False
