"""
Hotel Booking Specialist Microservice.
Provides independent A2A endpoints, agent card discovery, and Zero-Trust audience validation.
"""
import json
import logging
from typing import Dict, Any, Optional, List
from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field

from travel_concierge.tools.mock_services import MockHotelService, MockUsageMetadata
from travel_concierge.security.auth_guardrails import extract_token_claims
from travel_concierge.telemetry.tracer import get_tracer, TraceContextMiddleware

logger = logging.getLogger("travel_concierge.services.hotel")
tracer = get_tracer("travel_concierge.services.hotel")

app = FastAPI(
    title="Hotel Booking Specialist Service",
    version="2.0.0",
    description="Decoupled subagent service for hotel accommodation search and hold.",
)
app.add_middleware(TraceContextMiddleware)


def verify_hotel_audience(authorization: Optional[str] = Header(None)) -> Dict[str, Any]:
    """Enforces Zero-Trust token audience binding for hotel specialist."""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=401,
            detail="Missing or invalid Authorization header. Zero-Trust token required.",
        )
    token = authorization.split(" ", 1)[1].strip()
    claims = extract_token_claims(token)
    aud = claims.get("aud")
    expected = "hotel-booking-specialist"
    alt = "hotel-specialist"
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


class HotelHoldRequest(BaseModel):
    contextId: Optional[str] = None
    location: Optional[str] = "Tokyo Shinjuku"
    checkin: Optional[str] = "2026-09-01"
    checkout: Optional[str] = "2026-09-05"
    guests: Optional[int] = 1
    parts: Optional[List[Dict[str, Any]]] = None


@app.get("/health")
@app.get("/healthz")
def health():
    return {"status": "healthy", "service": "hotel_booking_specialist", "version": "2.0.0"}


@app.get("/.well-known/agent-card.json")
def get_agent_card():
    card = MockHotelService.get_agent_card()
    card["endpoints"] = {
        "message": "/messages",
        "search_and_hold": "/v1/search_and_hold",
    }
    return card


@app.post("/")
@app.post("/messages")
@app.post("/v1/search_and_hold")
async def search_and_hold(req: HotelHoldRequest, request: Request, authorization: Optional[str] = Header(None)):
    verify_hotel_audience(authorization)

    raw_body = {}
    try:
        raw_body = await request.json()
    except Exception:
        pass

    is_jsonrpc = isinstance(raw_body, dict) and ("jsonrpc" in raw_body or "method" in raw_body)
    rpc_id = raw_body.get("id") if is_jsonrpc else None
    method = raw_body.get("method", "SendMessage") if is_jsonrpc else None
    params = raw_body.get("params", {}) if is_jsonrpc else {}

    location = req.location or "Tokyo Shinjuku"
    if is_jsonrpc:
        message = params.get("message", {})
        parts = message.get("parts", [])
        if parts and isinstance(parts, list):
            for p in parts:
                if isinstance(p, dict) and p.get("text"):
                    txt = p["text"]
                    if " in " in txt:
                        location = txt.split(" in ", 1)[1].split(" for ", 1)[0].strip()
    elif req.parts and req.parts[0].get("text"):
        txt = req.parts[0]["text"]
        if " in " in txt:
            # simple extraction fallback
            location = txt.split(" in ", 1)[1].split(" for ", 1)[0].strip()

    checkin = req.checkin or "2026-09-01"
    checkout = req.checkout or "2026-09-05"
    guests = req.guests or 1

    with tracer.start_as_current_span("hotel_service_search_and_hold") as span:
        span.set_attribute("a2a.hotel.location", location)
        span.set_attribute("a2a.hotel.guests", guests)

        hotel_data = MockHotelService.search_hotels(location, checkin, checkout, guests)
        held_hotel = hotel_data["hotels"][0]
        task_id = f"task-{held_hotel['hotel_id']}"

        span.set_attribute("a2a.generated_task_id", task_id)

        metrics = {
            "prompt_tokens": 1800,
            "cached_tokens": 1350,
            "completion_tokens": 120,
            "total_tokens": 1920,
            "cache_hit_rate": 1350 / 1800,
        }

        if is_jsonrpc:
            msg_text = f"Held {held_hotel['name']} (rating: {held_hotel['rating']}, price: ${held_hotel['price_per_night_usd']}/night) under task ID {task_id}."
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
            "status": "held",
            "task_id": task_id,
            "taskId": task_id,
            "hotel": held_hotel,
            "price_per_night_usd": held_hotel["price_per_night_usd"],
            "metrics": metrics,
            "message": f"Held {held_hotel['name']} under task ID {task_id}.",
        }
