"""
Hotel Booking Specialist Microservice.
Provides independent A2A endpoints, agent card discovery, and Zero-Trust audience validation.
"""
import logging
from typing import Dict, Any, Optional, List
from fastapi import FastAPI, Header, HTTPException, Request
from pydantic import BaseModel, Field

from travel_concierge.tools.mock_services import MockHotelService, MockUsageMetadata
from travel_concierge.security.auth_guardrails import extract_token_claims
from travel_concierge.telemetry.tracer import get_tracer

logger = logging.getLogger("travel_concierge.services.hotel")
tracer = get_tracer("travel_concierge.services.hotel")

app = FastAPI(
    title="Hotel Booking Specialist Service",
    version="2.0.0",
    description="Decoupled subagent service for hotel accommodation search and hold.",
)


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


@app.post("/messages")
@app.post("/v1/search_and_hold")
def search_and_hold(req: HotelHoldRequest, request: Request, authorization: Optional[str] = Header(None)):
    verify_hotel_audience(authorization)

    location = req.location or "Tokyo Shinjuku"
    if req.parts and req.parts[0].get("text"):
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

        return {
            "status": "held",
            "task_id": task_id,
            "taskId": task_id,
            "hotel": held_hotel,
            "price_per_night_usd": held_hotel["price_per_night_usd"],
            "metrics": metrics,
            "message": f"Held {held_hotel['name']} under task ID {task_id}.",
        }
