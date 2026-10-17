"""
Agent Gateway Service (Policy Enforcement Point - PEP).
Enforces Zero-Trust authorization, audience binding, Model Armor guardrails,
and routes inter-agent communications between the Root Agent and Subagents.
"""
import os
import json
import logging
from typing import Dict, Any, Optional
from fastapi import FastAPI, Header, HTTPException, Request, Response
from fastapi.responses import JSONResponse
import httpx

from travel_concierge.config import settings
from travel_concierge.security.auth_guardrails import (
    validate_agent_gateway_headers,
    extract_token_claims,
)
from travel_concierge.security.gateway_policy import (
    AgentGatewayPolicy,
    GatewayPolicyViolationError,
    default_gateway_policy,
)
from travel_concierge.telemetry.tracer import get_tracer, inject_trace_context, TraceContextMiddleware

# Import subagent apps for in-process ASGI fallback
from travel_concierge.services.hotel_service import app as hotel_app
from travel_concierge.services.restaurant_service import app as restaurant_app
from travel_concierge.services.verification_service import app as verification_app

logger = logging.getLogger("travel_concierge.gateway")
tracer = get_tracer("travel_concierge.gateway")

app = FastAPI(
    title="Agent Gateway Policy Enforcement Point (PEP)",
    version="2.0.0",
    description="Central Policy Enforcement Point enforcing Zero-Trust identity, audience binding, and Model Armor.",
)

app.add_middleware(TraceContextMiddleware)

# Gateway policy instance with strict Zero-Trust & Model Armor
gateway_pep_policy = AgentGatewayPolicy(enforce_model_armor=True, enforce_auth_headers=True)

# Agent registry mapping
SUBAGENT_APPS = {
    "hotel_booking_specialist": hotel_app,
    "hotel-booking-specialist": hotel_app,
    "restaurant_booking_specialist": restaurant_app,
    "restaurant-booking-specialist": restaurant_app,
    "final_verification_agent": verification_app,
    "final-verification-agent": verification_app,
}

SUBAGENT_URLS = {
    "hotel_booking_specialist": lambda: settings.endpoints.hotel_service_url,
    "hotel-booking-specialist": lambda: settings.endpoints.hotel_service_url,
    "restaurant_booking_specialist": lambda: settings.endpoints.restaurant_service_url,
    "restaurant-booking-specialist": lambda: settings.endpoints.restaurant_service_url,
    "final_verification_agent": lambda: settings.endpoints.verification_service_url,
    "final-verification-agent": lambda: settings.endpoints.verification_service_url,
}


@app.get("/health")
@app.get("/healthz")
def health():
    return {"status": "healthy", "service": "agent_gateway", "version": "2.0.0"}


@app.get("/.well-known/agent-card.json")
def get_gateway_agent_card():
    return {
        "name": "agent_gateway_pep",
        "version": "2.0.0",
        "description": "Central Zero-Trust Policy Enforcement Point and Reverse Proxy for Subagents.",
        "capabilities": {
            "zero_trust_pep": True,
            "model_armor_enforcement": True,
            "subagent_routing": list(SUBAGENT_APPS.keys()),
        },
        "endpoints": {
            "route_message": "/v1/agents/{agent_name}/messages",
        },
    }


@app.get("/v1/agents/{agent_name}/.well-known/agent-card.json")
@app.get("/agents/{agent_name}/.well-known/agent-card.json")
async def get_subagent_card(agent_name: str, request: Request):
    """Proxies agent card discovery for a specific subagent."""
    target_app = SUBAGENT_APPS.get(agent_name)
    if not target_app:
        raise HTTPException(status_code=404, detail=f"Agent '{agent_name}' not found on Gateway.")

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=target_app), base_url="http://subagent.local") as client:
        resp = await client.get("/.well-known/agent-card.json")
        return JSONResponse(status_code=resp.status_code, content=resp.json())


@app.post("/v1/agents/{agent_name}/messages")
@app.post("/agents/{agent_name}")
@app.post("/agents/{agent_name}/")
@app.post("/agents/{agent_name}/messages")
async def route_agent_message(
    agent_name: str,
    request: Request,
    proxy_authorization: Optional[str] = Header(None),
    authorization: Optional[str] = Header(None),
    x_proxy_authorization: Optional[str] = Header(None),
    x_caller_identity: Optional[str] = Header(None),
):
    """
    Central Zero-Trust PEP Route.
    1. Validates Proxy-Authorization (caller's identity/SPIFFE).
    2. Validates Authorization (audience-bound token matching target subagent).
    3. Runs Model Armor inspection on request body.
    4. Forwards validated request to target subagent.
    """
    with tracer.start_as_current_span("agent_gateway_route_message") as span:
        span.set_attribute("gateway.target_agent", agent_name)

        target_app = SUBAGENT_APPS.get(agent_name)
        if not target_app:
            raise HTTPException(status_code=404, detail=f"Target subagent '{agent_name}' not registered in Gateway.")

        headers_dict = dict(request.headers)
        body_bytes = await request.body()

        # Step 1: Enforce Zero-Trust Headers
        # Note: Standard reverse proxies (like Google Cloud Run / GFE) strip hop-by-hop 'Proxy-Authorization' headers.
        # Fall back gracefully to X-Proxy-Authorization or X-Caller-Identity.
        caller_auth = (
            proxy_authorization
            or x_proxy_authorization
            or x_caller_identity
            or request.headers.get("x-proxy-authorization")
            or request.headers.get("x-caller-identity")
            or request.headers.get("proxy-authorization")
        )
        if not caller_auth or not caller_auth.startswith("Bearer "):
            span.set_attribute("gateway.policy.blocked", True)
            span.set_attribute("gateway.policy.reason", "missing_proxy_authorization")
            return JSONResponse(
                status_code=401,
                content={
                    "error": "Unauthorized",
                    "policy": "Agent Gateway Zero-Trust Policy",
                    "detail": "Missing or invalid Proxy-Authorization / X-Proxy-Authorization header (Caller SPIFFE Identity required).",
                },
            )

        if not authorization or not authorization.startswith("Bearer "):
            span.set_attribute("gateway.policy.blocked", True)
            span.set_attribute("gateway.policy.reason", "missing_authorization")
            return JSONResponse(
                status_code=401,
                content={
                    "error": "Unauthorized",
                    "policy": "Agent Gateway Zero-Trust Policy",
                    "detail": "Missing or invalid Authorization header (Audience-bound target token required).",
                },
            )

        # Step 2: Validate Audience Binding for Target Subagent
        token = authorization.split(" ", 1)[1].strip()
        claims = extract_token_claims(token)
        aud = claims.get("aud")
        expected_prefix = agent_name.replace("_", "-").split("-")[0]  # e.g., 'hotel', 'restaurant', 'verification'
        if not aud or expected_prefix not in str(aud):
            span.set_attribute("gateway.policy.blocked", True)
            span.set_attribute("gateway.policy.reason", "audience_mismatch")
            return JSONResponse(
                status_code=403,
                content={
                    "error": "Forbidden",
                    "policy": "Agent Gateway Zero-Trust Policy",
                    "violation_type": "audience_mismatch",
                    "detail": f"Audience mismatch: target '{agent_name}' cannot be accessed with token bound to '{aud}'.",
                },
            )

        # Step 3: Enforce Model Armor Guardrail on Payload
        try:
            gateway_pep_policy.enforce_request_policy(
                headers=headers_dict,
                body_bytes=body_bytes,
                span=span,
            )
        except GatewayPolicyViolationError as gpve:
            span.set_attribute("gateway.policy.blocked", True)
            span.set_attribute("gateway.policy.violation_category", gpve.violation_type)
            return JSONResponse(
                status_code=403,
                content={
                    "error": "Forbidden",
                    "policy": "Agent Gateway Model Armor Policy",
                    "violation_type": gpve.violation_type,
                    "detail": gpve.message,
                    "details": gpve.details,
                },
            )

        # Step 4: Forward Validated Request to Target Subagent
        target_url = SUBAGENT_URLS[agent_name]()
        subagent_headers = {
            "Authorization": authorization,
            "Content-Type": "application/json",
        }
        inject_trace_context(subagent_headers)

        # Forward via live network if target_url is an active external URL,
        # otherwise dispatch directly to the ASGI subagent app.
        if target_url.startswith("http://") or target_url.startswith("https://"):
            try:
                # If partner-cloud dummy domain or localhost, use local ASGI transport
                if "partner-cloud.com" in target_url or "example" in target_url or "localhost" in target_url:
                    async with httpx.AsyncClient(
                        transport=httpx.ASGITransport(app=target_app), base_url="http://subagent.local"
                    ) as client:
                        resp = await client.post(
                            "/messages",
                            content=body_bytes,
                            headers=subagent_headers,
                            timeout=10.0,
                        )
                        return JSONResponse(status_code=resp.status_code, content=resp.json())
                else:
                    async with httpx.AsyncClient() as client:
                        resp = await client.post(
                            f"{target_url.rstrip('/')}/messages",
                            content=body_bytes,
                            headers=subagent_headers,
                            timeout=15.0,
                        )
                        return JSONResponse(status_code=resp.status_code, content=resp.json())
            except Exception as e:
                logger.error(f"[Agent Gateway PEP] Error forwarding to subagent {agent_name}: {e}")
                # Fallback to local ASGI app
                async with httpx.AsyncClient(
                    transport=httpx.ASGITransport(app=target_app), base_url="http://subagent.local"
                ) as client:
                    resp = await client.post(
                        "/messages",
                        content=body_bytes,
                        headers=subagent_headers,
                        timeout=10.0,
                    )
                    return JSONResponse(status_code=resp.status_code, content=resp.json())
        else:
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=target_app), base_url="http://subagent.local"
            ) as client:
                resp = await client.post(
                    "/messages",
                    content=body_bytes,
                    headers=subagent_headers,
                    timeout=10.0,
                )
                return JSONResponse(status_code=resp.status_code, content=resp.json())
