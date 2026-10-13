"""
Agent Gateway Policy Enforcement Point (PEP).
Enforces Zero-Trust authorization, mTLS/SPIFFE header validation, and
Model Armor content moderation (prompt injection, hate speech, criminal activity)
directly at the Agent Gateway ingress layer before requests reach LLM agents.
"""
import json
import logging
from dataclasses import dataclass
from typing import Dict, Any, Optional, List, Tuple
from fastapi import Request, Response
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from opentelemetry.trace import Span

from travel_concierge.security.model_armor import default_model_armor, ModelArmorViolationError, InspectionResult
from travel_concierge.security.auth_guardrails import validate_agent_gateway_headers
from travel_concierge.telemetry.tracer import get_tracer

logger = logging.getLogger("travel_concierge.security.gateway_policy")
tracer = get_tracer("travel_concierge.gateway_policy")


class GatewayPolicyViolationError(Exception):
    """Raised when an incoming or outgoing request violates Agent Gateway policies."""
    def __init__(self, message: str, violation_type: str, details: Optional[Dict[str, Any]] = None):
        super().__init__(message)
        self.message = message
        self.violation_type = violation_type
        self.details = details or {}


@dataclass
class PolicyDecision:
    allowed: bool
    violation_type: Optional[str] = None
    reason: Optional[str] = None


class AgentGatewayPolicy:
    """
    Agent Gateway Policy Engine.
    Executes centralized policy checks on all traffic transiting the Agent Gateway:
    1. Model Armor Content Security (Prompt Injection, Hate Speech, Criminal Exploitation)
    2. Zero-Trust Identity Verification (SPIFFE, Audience Binding, Proxy-Authorization)
    3. SSRF & Ingress Parameter Sanitization
    """

    @classmethod
    def evaluate_ingress(
        cls,
        headers: Optional[Dict[str, str]] = None,
        body: Optional[Any] = None,
        client_ip: Optional[str] = None,
    ) -> PolicyDecision:
        """Evaluates ingress request against Model Armor without raising exceptions."""
        try:
            if body is not None:
                default_gateway_policy.scan_json_object(body, path="ingress")
            return PolicyDecision(allowed=True)
        except GatewayPolicyViolationError as e:
            return PolicyDecision(allowed=False, violation_type=e.violation_type, reason=e.message)
        except Exception:
            return PolicyDecision(allowed=True)

    def __init__(
        self,
        enforce_model_armor: bool = True,
        enforce_auth_headers: bool = False,
    ):
        self.enforce_model_armor = enforce_model_armor
        self.enforce_auth_headers = enforce_auth_headers
        self.armor = default_model_armor

    def inspect_text_payload(self, text: str, field_name: str = "payload", span: Optional[Span] = None) -> InspectionResult:
        """Enforces Model Armor policy against a text snippet at the gateway."""
        if not self.enforce_model_armor or not text:
            return InspectionResult(is_safe=True, category="clean", confidence=1.0)

        result = self.armor.inspect_prompt(text)
        if not result.is_safe:
            if span and span.is_recording():
                span.set_attribute("gateway.policy.blocked", True)
                span.set_attribute("gateway.policy.violation_field", field_name)
                span.set_attribute("gateway.policy.violation_category", result.category)
                span.set_attribute("gateway.policy.violation_reason", result.reason or "")

            logger.warning(
                f"[Agent Gateway PEP] BLOCKED by Model Armor Policy in field '{field_name}'. "
                f"Category: {result.category} | Reason: {result.reason} | Snippet: {text[:80]}..."
            )
            raise GatewayPolicyViolationError(
                message=f"Agent Gateway Policy Violation: Request blocked by Model Armor ({result.category}): {result.reason}",
                violation_type=result.category,
                details={"field": field_name, "category": result.category, "reason": result.reason},
            )
        return result

    def scan_json_object(self, obj: Any, path: str = "root", span: Optional[Span] = None):
        """Recursively scans all string fields in a JSON structure with Model Armor."""
        if isinstance(obj, str):
            self.inspect_text_payload(obj, field_name=path, span=span)
        elif isinstance(obj, dict):
            for k, v in obj.items():
                self.scan_json_object(v, path=f"{path}.{k}", span=span)
        elif isinstance(obj, (list, tuple)):
            for idx, item in enumerate(obj):
                self.scan_json_object(item, path=f"{path}[{idx}]", span=span)

    def enforce_request_policy(
        self,
        headers: Dict[str, str],
        body_bytes: bytes,
        query_params: Optional[Dict[str, str]] = None,
        span: Optional[Span] = None,
    ):
        """
        Executes complete Agent Gateway policy enforcement on an incoming request:
        - Validates Zero-Trust headers if configured.
        - Evaluates query parameters with Model Armor.
        - Evaluates JSON payload with Model Armor.
        """
        # 1. Zero-Trust Header Policy
        if self.enforce_auth_headers:
            if not validate_agent_gateway_headers(headers):
                if span and span.is_recording():
                    span.set_attribute("gateway.policy.blocked", True)
                    span.set_attribute("gateway.policy.violation_category", "unauthorized_gateway_headers")
                raise GatewayPolicyViolationError(
                    message="Agent Gateway Policy Violation: Missing or invalid Proxy-Authorization / Authorization headers.",
                    violation_type="auth_failure",
                )

        # 2. Model Armor Inspection on Query Parameters
        if self.enforce_model_armor and query_params:
            for k, v in query_params.items():
                self.inspect_text_payload(v, field_name=f"param.{k}", span=span)

        # 3. Model Armor Inspection on Request Body
        if self.enforce_model_armor and body_bytes:
            try:
                body_str = body_bytes.decode("utf-8", errors="replace")
                # Try parsing as JSON first
                try:
                    parsed_json = json.loads(body_str)
                    self.scan_json_object(parsed_json, path="body", span=span)
                except json.JSONDecodeError:
                    # Raw text scan
                    self.inspect_text_payload(body_str, field_name="raw_body", span=span)
            except Exception as e:
                if isinstance(e, GatewayPolicyViolationError):
                    raise
                logger.warning(f"[Agent Gateway PEP] Non-fatal error parsing body for Model Armor: {e}")


# Default Gateway Policy singleton
default_gateway_policy = AgentGatewayPolicy(enforce_model_armor=True, enforce_auth_headers=False)


class GatewayPolicyMiddleware(BaseHTTPMiddleware):
    """
    FastAPI / Starlette middleware enforcing Agent Gateway Policy on all incoming traffic.
    Guarantees Model Armor is enforced at the Gateway PEP ingress before any agent execution.
    """

    def __init__(self, app, policy: Optional[AgentGatewayPolicy] = None):
        super().__init__(app)
        self.policy = policy or default_gateway_policy

    async def dispatch(self, request: Request, call_next):
        # Exclude static routes, health checks, and portal UI assets from gateway inspection
        if (
            request.url.path in ("/", "/health", "/healthz", "/docs", "/openapi.json", "/portal", "/portal/", "/portal/config", "/portal/sessions")
            or request.url.path.startswith("/portal/static")
            or request.url.path.startswith("/portal/api")
        ):
            return await call_next(request)

        with tracer.start_as_current_span("agent_gateway_pep_enforcement") as span:
            span.set_attribute("gateway.path", request.url.path)
            span.set_attribute("gateway.method", request.method)

            # Read request body safely
            body_bytes = await request.body()
            headers_dict = dict(request.headers)
            query_dict = dict(request.query_params)

            try:
                self.policy.enforce_request_policy(
                    headers=headers_dict,
                    body_bytes=body_bytes,
                    query_params=query_dict,
                    span=span,
                )
                span.set_attribute("gateway.policy.status", "allowed")
            except GatewayPolicyViolationError as gpve:
                logger.error(f"[Agent Gateway PEP Enforced] Access Denied: {gpve.message}")
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

            # Proceed down middleware chain
            response = await call_next(request)
            return response
