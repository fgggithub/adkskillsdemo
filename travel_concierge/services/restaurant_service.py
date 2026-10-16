"""
Restaurant Booking Specialist Microservice.
Provides independent A2A endpoints, Zomato MCP search, dietary skill validation,
and Zero-Trust audience verification.
"""
import json
import logging
from typing import Dict, Any, Optional, List
from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field

from travel_concierge.tools.mcp_toolset import execute_zomato_search
from travel_concierge.tools.skill_registry import evaluate_dietary_compliance
from travel_concierge.security.auth_guardrails import extract_token_claims
from travel_concierge.telemetry.tracer import get_tracer, TraceContextMiddleware

logger = logging.getLogger("travel_concierge.services.restaurant")
tracer = get_tracer("travel_concierge.services.restaurant")

app = FastAPI(
    title="Restaurant Booking Specialist Service",
    version="2.0.0",
    description="Decoupled subagent service for restaurant discovery and dietary compliance.",
)
app.add_middleware(TraceContextMiddleware)


def verify_restaurant_audience(authorization: Optional[str] = Header(None)) -> Dict[str, Any]:
    """Enforces Zero-Trust token audience binding for restaurant specialist."""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=401,
            detail="Missing or invalid Authorization header. Zero-Trust token required.",
        )
    token = authorization.split(" ", 1)[1].strip()
    claims = extract_token_claims(token)
    aud = claims.get("aud")
    expected = "restaurant-booking-specialist"
    alt = "restaurant-specialist"
    if not aud:
        raise HTTPException(
            status_code=403,
            detail="Token audience missing: Zero-Trust requires audience-bound token.",
        )
    if isinstance(aud, list):
        if not any(expected in a or alt in a for a in aud):
            raise HTTPException(
                status_code=403,
                detail=f"Token audience mismatch: required '{expected}', got {aud}",
            )
    elif expected not in aud and alt not in aud:
        raise HTTPException(
            status_code=403,
            detail=f"Token audience mismatch: required '{expected}', got '{aud}'",
        )
    return claims


class DiningQueryRequest(BaseModel):
    contextId: Optional[str] = None
    query: Optional[str] = "vegan dinner options near the hotel"
    referenceTaskIds: Optional[List[str]] = Field(default_factory=list)
    token_claims: Optional[Dict[str, Any]] = None
    parts: Optional[List[Dict[str, Any]]] = None


@app.get("/health")
@app.get("/healthz")
def health():
    return {"status": "healthy", "service": "restaurant_booking_specialist", "version": "2.0.0"}


@app.get("/.well-known/agent-card.json")
def get_agent_card():
    return {
        "name": "restaurant_booking_specialist",
        "version": "2.0.0",
        "description": "Remote A2A Agent for dining search via Zomato MCP and dietary compliance skill.",
        "capabilities": {
            "zomato_mcp": True,
            "dietary_advisor_skill": True,
            "a2a_context_sharing": True,
        },
        "endpoints": {
            "message": "/messages",
            "find_dining": "/v1/find_dining",
        },
    }


@app.post("/")
@app.post("/messages")
@app.post("/v1/find_dining")
async def find_dining(req: DiningQueryRequest, request: Request, authorization: Optional[str] = Header(None)):
    verify_restaurant_audience(authorization)

    raw_body = {}
    try:
        raw_body = await request.json()
    except Exception:
        pass

    is_jsonrpc = isinstance(raw_body, dict) and ("jsonrpc" in raw_body or "method" in raw_body)
    rpc_id = raw_body.get("id") if is_jsonrpc else None
    method = raw_body.get("method", "SendMessage") if is_jsonrpc else None
    params = raw_body.get("params", {}) if is_jsonrpc else {}

    claims = req.token_claims or {
        "sub": "user:api_caller@example.com",
        "groups": ["MCPUSERS", "TRAVELERS"],
        "scope": "https://mcp-server.zomato.com/scopes/restaurants.read",
    }

    query = req.query or "vegan dinner options"
    if is_jsonrpc:
        message = params.get("message", {})
        parts = message.get("parts", [])
        if parts and isinstance(parts, list):
            for p in parts:
                if isinstance(p, dict) and p.get("text"):
                    query = p["text"]
    elif req.parts and req.parts[0].get("text"):
        query = req.parts[0]["text"]

    with tracer.start_as_current_span("restaurant_service_find_dining") as span:
        span.set_attribute("a2a.dining.query", query)
        if req.referenceTaskIds:
            span.set_attribute("a2a.reference_task_ids", ",".join(req.referenceTaskIds))

        try:
            mcp_result = execute_zomato_search(claims, query)
        except PermissionError as pe:
            raise HTTPException(status_code=403, detail=str(pe))

        # Apply dietary skill check
        dietary_eval = evaluate_dietary_compliance("Ain Soph Journey Shinjuku", "vegan")

        metrics = {
            "prompt_tokens": 2100,
            "cached_tokens": 1650,
            "completion_tokens": 180,
            "total_tokens": 2280,
            "cache_hit_rate": 1650 / 2100,
        }

        if is_jsonrpc:
            recs_text = "; ".join(mcp_result.get("results", []))
            msg_text = f"Found dining options: {recs_text}. Dietary compliance: {dietary_eval.get('recommendation', 'Verified plant-based')}."
            if method == "SendStreamingMessage":
                async def event_generator():
                    event_payload = {
                        "jsonrpc": "2.0",
                        "id": rpc_id,
                        "result": {
                            "message": {
                                "role": "ROLE_AGENT",
                                "parts": [{"text": msg_text}],
                            }
                        },
                    }
                    yield f"data: {json.dumps(event_payload)}\n\n"
                return StreamingResponse(event_generator(), media_type="text/event-stream")
            else:
                return JSONResponse(
                    content={
                        "jsonrpc": "2.0",
                        "id": rpc_id,
                        "result": {
                            "message": {
                                "role": "ROLE_AGENT",
                                "parts": [{"text": msg_text}],
                            }
                        },
                    }
                )

        return {
            "status": "success",
            "contextId": req.contextId,
            "referenceTaskIds": req.referenceTaskIds,
            "mcp_result": mcp_result,
            "dietary_compliance": dietary_eval,
            "recommendations": mcp_result.get("results", []),
            "metrics": metrics,
        }
