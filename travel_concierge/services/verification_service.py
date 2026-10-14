"""
Final Verification Sub-Agent Microservice.
Provides independent A2A endpoints, HITL task streaming/state management,
and Zero-Trust audience verification.
"""
import logging
from typing import Dict, Any, Optional, List
from fastapi import FastAPI, Header, HTTPException, Request
from pydantic import BaseModel, Field

from travel_concierge.tools.mock_services import MockVerificationService, MockAgentResponse
from travel_concierge.security.auth_guardrails import extract_token_claims
from travel_concierge.telemetry.tracer import get_tracer, TraceContextMiddleware

logger = logging.getLogger("travel_concierge.services.verification")
tracer = get_tracer("travel_concierge.services.verification")

app = FastAPI(
    title="Final Verification Agent Service",
    version="2.0.0",
    description="Decoupled subagent service for HITL verification and payment confirmation.",
)
app.add_middleware(TraceContextMiddleware)


def verify_verification_audience(authorization: Optional[str] = Header(None)) -> Dict[str, Any]:
    """Enforces Zero-Trust token audience binding for verification agent."""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=401,
            detail="Missing or invalid Authorization header. Zero-Trust token required.",
        )
    token = authorization.split(" ", 1)[1].strip()
    claims = extract_token_claims(token)
    aud = claims.get("aud")
    expected = "final-verification-agent"
    alts = ["verification-agent", "verification-specialist"]
    if not aud:
        raise HTTPException(
            status_code=403,
            detail="Token audience missing: Zero-Trust requires audience-bound token.",
        )
    if isinstance(aud, list):
        if not any(expected in a or any(alt in a for alt in alts) for a in aud):
            raise HTTPException(
                status_code=403,
                detail=f"Token audience mismatch: required '{expected}', got {aud}",
            )
    elif expected not in aud and not any(alt in aud for alt in alts):
        raise HTTPException(
            status_code=403,
            detail=f"Token audience mismatch: required '{expected}', got '{aud}'",
        )
    return claims


class VerificationTaskRequest(BaseModel):
    contextId: Optional[str] = None
    referenceTaskIds: Optional[List[str]] = Field(default_factory=list)
    auto_confirm: bool = True
    user_confirmation: Optional[str] = None
    parts: Optional[List[Dict[str, Any]]] = None


@app.get("/health")
@app.get("/healthz")
def health():
    return {"status": "healthy", "service": "final_verification_agent", "version": "2.0.0"}


@app.get("/.well-known/agent-card.json")
def get_agent_card():
    return {
        "name": "final_verification_agent",
        "version": "2.0.0",
        "description": "Remote A2A Agent for HITL task streaming and payment verification.",
        "capabilities": {
            "task_streaming": True,
            "hitl_interruption": True,
            "push_notification": True,
        },
        "endpoints": {
            "message": "/messages",
            "verify": "/v1/tasks/verify",
        },
    }


@app.post("/messages")
@app.post("/v1/tasks/verify")
def verify_task(req: VerificationTaskRequest, request: Request, authorization: Optional[str] = Header(None)):
    verify_verification_audience(authorization)

    current_task_id = req.referenceTaskIds[0] if req.referenceTaskIds else "task-hotel-shinjuku-99"

    with tracer.start_as_current_span("verification_service_verify_task") as span:
        span.set_attribute("a2a.task_id", current_task_id)

        # Simulate HITL interrupt check
        interrupt_msg = "Please confirm authorization to charge $420.00 to card ending in 4242 for Shinjuku stay."
        if not req.auto_confirm and not req.user_confirmation:
            return {
                "status": "pending",
                "task_id": current_task_id,
                "state": "input-required",
                "interrupted": True,
                "interrupt_message": interrupt_msg,
                "message": interrupt_msg,
            }

        # Confirmed
        conf_response = MockVerificationService.resume_task(
            task_id=current_task_id,
            user_confirmation=req.user_confirmation or "Auto-confirmed payment",
        )

        metrics = {
            "prompt_tokens": 1200,
            "cached_tokens": 900,
            "completion_tokens": 80,
            "total_tokens": 1280,
            "cache_hit_rate": 900 / 1200,
        }

        return {
            "status": "success",
            "task_id": current_task_id,
            "state": "completed",
            "interrupted": True,
            "interrupt_message": interrupt_msg,
            "confirmation_code": "CONF-TOK-88991",
            "message": conf_response.text,
            "metrics": metrics,
        }
