"""
FastAPI Router and Endpoints for the StreamAssist Web Portal.
Serves interactive Web UI and SSE Streaming endpoints.
"""

import os
import json
import logging
from typing import Optional, Dict, Any
from pathlib import Path

from fastapi import APIRouter, Request, Response, HTTPException
from fastapi.responses import HTMLResponse, StreamingResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from travel_concierge.config import settings
from travel_concierge.portal.stream_assist_service import stream_assist_service, _PORTAL_SESSIONS
from travel_concierge.telemetry.budget_tracker import budget_tracker

logger = logging.getLogger("travel_concierge.portal")

portal_router = APIRouter(prefix="/portal", tags=["Web Portal"])

STATIC_DIR = Path(__file__).parent / "static"
STATIC_DIR.mkdir(parents=True, exist_ok=True)


class StreamAssistPortalRequest(BaseModel):
    query: str
    session_id: Optional[str] = None
    destination: Optional[str] = None
    backend: Optional[str] = "concierge"  # "concierge" | "discovery_engine"
    engine_id: Optional[str] = None
    auto_confirm: Optional[bool] = True


@portal_router.get("/config")
def get_portal_config():
    """Returns portal configuration and budget status."""
    budget = budget_tracker.get_budget_status()
    return {
        "project_id": settings.PROJECT_ID or "qwiklabs-gcp-01-f54046474f73",
        "region": settings.REGION or "us-central1",
        "default_engine_id": os.getenv("GEMINI_ENTERPRISE_ENGINE_ID", "fdedemoapp"),
        "active_model": settings.DEFAULT_MODEL,
        "escalation_model": "gemini-3.5",
        "budget": budget,
        "security_policy": "Agent Gateway Model Armor Policy (Active)",
        "features": [
            "Discovery Engine StreamAssist API",
            "Multi-Agent A2A Protocol",
            "Model Armor Ingress Guard",
            "Dynamic Model Escalation",
            "Explicit Context Caching (75% discount)",
            "Multi-Turn Session Refinement",
        ]
    }


@portal_router.get("/sessions")
def list_sessions():
    """Lists active portal conversation sessions."""
    return {"sessions": list(_PORTAL_SESSIONS.values())}


@portal_router.post("/sessions/clear")
def clear_sessions():
    """Resets conversational session history."""
    _PORTAL_SESSIONS.clear()
    return {"status": "cleared", "message": "All session states reset."}


@portal_router.post("/api/stream")
async def stream_assist_endpoint(req: StreamAssistPortalRequest):
    """
    Server-Sent Events (SSE) streaming endpoint wrapping the StreamAssist API.
    Conforms to https://docs.cloud.google.com/gemini/enterprise/docs/get-answers-from-streamassist
    """
    if not req.query or not req.query.strip():
        raise HTTPException(status_code=400, detail="Query text cannot be empty.")

    backend = req.backend or "concierge"
    project_id = settings.PROJECT_ID or "qwiklabs-gcp-01-f54046474f73"
    location = settings.REGION or "us-central1"
    engine_id = req.engine_id or os.getenv("GEMINI_ENTERPRISE_ENGINE_ID", "fdedemoapp")

    def event_generator():
        try:
            if backend == "discovery_engine":
                stream = stream_assist_service.stream_assist_discovery_engine_api(
                    query=req.query,
                    project_id=project_id,
                    location=location,
                    engine_id=engine_id,
                    session_id=req.session_id,
                )
            else:
                stream = stream_assist_service.stream_assist_concierge(
                    query=req.query,
                    session_id=req.session_id,
                    destination=req.destination,
                    auto_confirm=req.auto_confirm if req.auto_confirm is not None else True,
                )

            for chunk in stream:
                yield f"data: {json.dumps(chunk)}\n\n"

            yield "data: [DONE]\n\n"
        except Exception as e:
            logger.exception("Error during StreamAssist execution: %s", str(e))
            err_payload = {
                "answer": {
                    "state": "FAILED",
                    "answerText": f"StreamAssist Internal Error: {str(e)}",
                }
            }
            yield f"data: {json.dumps(err_payload)}\n\n"
            yield "data: [DONE]\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        }
    )


@portal_router.get("", response_class=HTMLResponse)
@portal_router.get("/", response_class=HTMLResponse)
def get_portal_page():
    """Serves the Web Portal HTML page."""
    index_file = STATIC_DIR / "index.html"
    if not index_file.exists():
        return HTMLResponse("<h1>Web Portal loading...</h1>", status_code=200)
    with open(index_file, "r", encoding="utf-8") as f:
        return HTMLResponse(content=f.read(), status_code=200)
