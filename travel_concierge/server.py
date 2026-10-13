"""
FastAPI production application exposing A2A endpoints, webhooks, and trip orchestration API.
"""
import os
import logging
from typing import Dict, Any, Optional, List
from fastapi import FastAPI, Header, HTTPException, Depends, Request
from pydantic import BaseModel, Field

from travel_concierge.config import settings
from travel_concierge.telemetry.tracer import init_tracer
from travel_concierge.agents.root_agent import TravelConciergeRootAgent
from travel_concierge.security.auth_guardrails import validate_agent_gateway_headers

from travel_concierge.security.gateway_policy import GatewayPolicyMiddleware, default_gateway_policy
from fastapi.staticfiles import StaticFiles
from travel_concierge.portal.portal_server import portal_router, STATIC_DIR

logger = logging.getLogger("travel_concierge.server")
init_tracer("travel_concierge_api")

app = FastAPI(
    title="Travel Concierge Multi-Agent Service",
    version="2.0.0",
    description="Enterprise Travel Concierge A2A orchestrator with Agent Gateway PEP, Model Armor, Context Caching, and OpenTelemetry.",
)

# Enforce Agent Gateway Policy (Zero-Trust & Model Armor) on all incoming requests
app.add_middleware(GatewayPolicyMiddleware, policy=default_gateway_policy)

# Mount Web Portal (Discovery Engine StreamAssist Webapp)
app.include_router(portal_router)
app.mount("/portal/static", StaticFiles(directory=str(STATIC_DIR)), name="portal_static")

root_agent = TravelConciergeRootAgent()


class TripPlanRequest(BaseModel):
    destination: str = Field(default="Tokyo Shinjuku", description="Target destination")
    dining_query: str = Field(default="vegan dinner options", description="Food & dining preferences")
    context_id: Optional[str] = Field(default=None, description="Trip session context ID")
    auto_confirm: bool = Field(default=True, description="Whether to auto-authorize HITL verification")
    token_claims: Optional[Dict[str, Any]] = Field(
        default_factory=lambda: {
            "sub": "user:api_caller@example.com",
            "groups": ["MCPUSERS", "TRAVELERS"],
            "scope": "https://mcp-server.zomato.com/scopes/restaurants.read",
        }
    )


class WebhookEventPayload(BaseModel):
    event_type: str
    task_id: str
    status: str
    payload: Optional[Dict[str, Any]] = None


@app.get("/health")
@app.get("/healthz")
def health_check():
    """Liveness probe and public health check."""
    return {"status": "healthy", "service": "travel_concierge", "version": "2.0.0"}


@app.get("/")
def root_route(request: Request):
    """Directs browser clients to Web Portal, and returns JSON health for API probes."""
    accept = request.headers.get("accept", "")
    if "text/html" in accept:
        from fastapi.responses import RedirectResponse
        return RedirectResponse(url="/portal")
    return {"status": "healthy", "service": "travel_concierge", "version": "2.0.0"}


@app.get("/.well-known/agent-card.json")
def get_agent_card():
    """A2A discovery agent card metadata."""
    return {
        "name": "travel_concierge_2.0",
        "version": "2.0.0",
        "description": "Enterprise Travel Dining & Hotel Concierge Root Agent.",
        "capabilities": {
            "subagents": ["hotel_booking_specialist", "restaurant_booking_specialist", "final_verification_agent"],
            "context_caching": True,
            "opentelemetry_tracing": True,
            "task_streaming": True,
        },
        "endpoints": {
            "plan_trip": "/v1/trips/plan",
            "webhook_receiver": "/a2a/webhooks/push",
        },
    }


class TripRefineRequest(BaseModel):
    context_id: str = Field(description="Trip session context ID to refine")
    refinement_query: str = Field(description="Refinement instruction (e.g., 'Switch to 5-star hotel')")
    auto_confirm: bool = Field(default=True, description="Whether to auto-authorize HITL verification")
    token_claims: Optional[Dict[str, Any]] = None


@app.post("/v1/trips/plan")
async def plan_trip_endpoint(req: TripPlanRequest, request: Request):
    """
    Primary API endpoint to orchestrate travel planning across hotel, dining, and verification agents.
    """
    try:
        result = root_agent.plan_trip(
            destination=req.destination,
            dining_query=req.dining_query,
            context_id=req.context_id,
            token_claims=req.token_claims,
            auto_confirm_booking=req.auto_confirm,
        )
        return {
            "status": "success",
            "context_id": result["context_id"],
            "destination": result["destination"],
            "model_escalation": result.get("model_escalation"),
            "hotel": str(result["hotel_booking"]["response"]),
            "dining": str(result["restaurant_recommendations"]["response"]),
            "verification": result["verification"]["state"],
            "telemetry": result["telemetry"],
            "budget": result.get("budget"),
        }
    except PermissionError as pe:
        raise HTTPException(status_code=403, detail=str(pe))
    except Exception as e:
        logger.exception("Error executing trip planning")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/v1/trips/refine")
async def refine_trip_endpoint(req: TripRefineRequest, request: Request):
    """
    Multi-turn conversational refinement endpoint.
    Refines hotel or restaurant recommendations for an existing context session.
    """
    try:
        result = root_agent.refine_itinerary(
            context_id=req.context_id,
            refinement_query=req.refinement_query,
            token_claims=req.token_claims,
            auto_confirm_booking=req.auto_confirm,
        )
        return {
            "status": "success",
            "context_id": result["context_id"],
            "turn": result.get("turn"),
            "model_escalation": result.get("model_escalation"),
            "hotel": str(result["hotel_booking"]["response"]),
            "dining": str(result["restaurant_recommendations"]["response"]),
            "verification": result["verification"]["state"],
            "telemetry": result["telemetry"],
            "budget": result.get("budget"),
        }
    except PermissionError as pe:
        raise HTTPException(status_code=403, detail=str(pe))
    except Exception as e:
        logger.exception("Error executing trip refinement")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/a2a/webhooks/push")
async def handle_webhook_push(event: WebhookEventPayload, authorization: Optional[str] = Header(None)):
    """Receives asynchronous push notifications from remote A2A subagents."""
    logger.info(f"Received Webhook event: {event.event_type} for task: {event.task_id}")
    return {"status": "acknowledged", "task_id": event.task_id}


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", "8080"))
    uvicorn.run(app, host="0.0.0.0", port=port)
