"""
Agent Gateway Client for Zero-Trust Inter-Agent Communication.
Routes A2A requests from Root Agent through the central Policy Enforcement Point (PEP).
"""
import os
import logging
from typing import Dict, Any, Optional
import httpx

from travel_concierge.config import settings
from travel_concierge.security.auth_guardrails import build_gateway_headers
from travel_concierge.security.gateway_policy import GatewayPolicyViolationError
from travel_concierge.telemetry.tracer import inject_trace_context

logger = logging.getLogger("travel_concierge.gateway.client")

# Predefined audience tokens for subagents
DEFAULT_SUBAGENT_TOKENS = {
    "hotel-booking-specialist": "eyJhbGciOiJSUzI1NiJ9.eyJhdWQiOiJob3RlbC1ib29raW5nLXNwZWNpYWxpc3QifQ.sig",
    "hotel_booking_specialist": "eyJhbGciOiJSUzI1NiJ9.eyJhdWQiOiJob3RlbC1ib29raW5nLXNwZWNpYWxpc3QifQ.sig",
    "restaurant-booking-specialist": "eyJhbGciOiJSUzI1NiJ9.eyJhdWQiOiJyZXN0YXVyYW50LWJvb2tpbmctc3BlY2lhbGlzdCJ9.sig",
    "restaurant_booking_specialist": "eyJhbGciOiJSUzI1NiJ9.eyJhdWQiOiJyZXN0YXVyYW50LWJvb2tpbmctc3BlY2lhbGlzdCJ9.sig",
    "final-verification-agent": "eyJhbGciOiJSUzI1NiJ9.eyJhdWQiOiJmaW5hbC12ZXJpZmljYXRpb24tYWdlbnQifQ.sig",
    "final_verification_agent": "eyJhbGciOiJSUzI1NiJ9.eyJhdWQiOiJmaW5hbC12ZXJpZmljYXRpb24tYWdlbnQifQ.sig",
}


DEFAULT_CALLER_SPIFFE = "spiffe://prod.corp/agent/travel-concierge"


def send_gateway_message(
    agent_name: str,
    payload: Dict[str, Any],
    caller_spiffe_token: Optional[str] = None,
    target_token: Optional[str] = None,
    extra_headers: Optional[Dict[str, str]] = None,
) -> Dict[str, Any]:
    """
    Sends an A2A message through the Agent Gateway PEP.
    Enforces Zero-Trust headers and raises GatewayPolicyViolationError on policy blocks.
    """
    caller_spiffe = caller_spiffe_token or DEFAULT_CALLER_SPIFFE
    target_tok = target_token or DEFAULT_SUBAGENT_TOKENS.get(
        agent_name, "eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCIsImF1ZCI6IiJ9.payload.signature"
    )

    headers = build_gateway_headers(
        caller_spiffe_gateway_token=caller_spiffe,
        target_subagent_access_token=target_tok,
        extra_headers=extra_headers,
    )
    headers["Content-Type"] = "application/json"

    gateway_url = settings.endpoints.agent_gateway_url

    # In live Cloud Run deployment, route to the Gateway HTTP endpoint
    # In test/local environments, use the ASGI transport directly
    from travel_concierge.gateway.server import app as gateway_app

    endpoint_path = f"/v1/agents/{agent_name}/messages"

    if (
        gateway_url
        and not "internal.bank.example" in gateway_url
        and not "localhost" in gateway_url
        and (gateway_url.startswith("http://") or gateway_url.startswith("https://"))
    ):
        target_endpoint = f"{gateway_url.rstrip('/')}{endpoint_path}"
        with httpx.Client(timeout=15.0) as client:
            resp = client.post(target_endpoint, json=payload, headers=headers)
    else:
        # Self-contained ASGI transport
        transport = httpx.ASGITransport(app=gateway_app)
        with httpx.Client(transport=transport, base_url="http://gateway.local", timeout=15.0) as client:
            resp = client.post(endpoint_path, json=payload, headers=headers)

    if resp.status_code == 403:
        err_data = resp.json()
        raise GatewayPolicyViolationError(
            message=err_data.get("detail", "Blocked by Agent Gateway PEP"),
            violation_type=err_data.get("violation_type", "gateway_policy_violation"),
            details=err_data.get("details", {}),
        )
    elif resp.status_code == 401:
        err_data = resp.json()
        raise PermissionError(f"401 Unauthorized at Agent Gateway PEP: {err_data.get('detail')}")
    elif resp.status_code >= 400:
        raise RuntimeError(f"Gateway returned HTTP {resp.status_code}: {resp.text}")

    return resp.json()
