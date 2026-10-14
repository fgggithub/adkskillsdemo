"""
Hotel Booking Specialist Sub-Agent implementation using RemoteA2aAgent.
"""
import logging
from typing import Dict, Any, Optional, List

from google.adk.agents.remote_a2a_agent import RemoteA2aAgent, AGENT_CARD_WELL_KNOWN_PATH

from travel_concierge.config import settings
from travel_concierge.security.ssrf_validator import validate_webhook_url
from travel_concierge.security.auth_guardrails import build_gateway_headers
from travel_concierge.telemetry.tracer import get_tracer
from travel_concierge.telemetry.cost_tracker import track_llm_telemetry
from travel_concierge.tools.mock_services import MockHotelService, MockAgentResponse, MockUsageMetadata

logger = logging.getLogger("travel_concierge.hotel_agent")
tracer = get_tracer("travel_concierge.hotel_agent")


def create_hotel_subagent(
    endpoint_url: Optional[str] = None,
    webhook_callback_url: Optional[str] = None,
    use_gateway: bool = False,
    auth_token: str = "signed-jwt-or-opaque-auth-token",
) -> RemoteA2aAgent:
    """
    Factory creating RemoteA2aAgent with validated SSRF webhook configuration
    and Agent Gateway routing.
    """
    callback_url = webhook_callback_url or settings.endpoints.webhook_callback_url
    validated_webhook = validate_webhook_url(callback_url)

    if use_gateway:
        agent_card_url = f"{settings.endpoints.agent_gateway_url}/agents/hotel-booking-specialist"
    else:
        base_url = endpoint_url or settings.endpoints.hotel_service_url
        agent_card_url = f"{base_url.rstrip('/')}{AGENT_CARD_WELL_KNOWN_PATH}"

    agent = RemoteA2aAgent(
        name="hotel_booking_specialist",
        description="Handles finding and booking hotel accommodations on remote cloud service.",
        agent_card=agent_card_url,
        use_legacy=False,
    )
    # Store push notification config in metadata
    setattr(agent, "_push_notification_config", {"url": validated_webhook, "token": auth_token})
    return agent


class HotelAgentWrapper:
    """
    Operational wrapper for the Remote Hotel Sub-Agent, managing Agent-to-Agent
    handshakes, task token creation, and telemetry tracing.
    """

    def __init__(self, agent: Optional[RemoteA2aAgent] = None, use_gateway: bool = True):
        self.use_gateway = use_gateway
        self.agent = agent or create_hotel_subagent(use_gateway=use_gateway)

    def search_and_hold_hotel(
        self,
        context_id: str,
        location: str,
        checkin: str = "2026-09-01",
        checkout: str = "2026-09-05",
        guests: int = 1,
        caller_spiffe_token: Optional[str] = None,
        target_token: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Queries hotel availability and reserves a temporary hold, generating
        a reference task ID for downstream agents.
        """
        with tracer.start_as_current_span("delegate_hotel_agent") as span:
            span.set_attribute("a2a.context_id", context_id)
            span.set_attribute("a2a.hotel.location", location)

            headers = build_gateway_headers(
                caller_spiffe_gateway_token=caller_spiffe_token or "spiffe://prod.corp/agent/travel-concierge",
                target_subagent_access_token=target_token or "eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCIsImF1ZCI6ImhvdGVsLXNwZWNpYWxpc3QifQ.payload.sig",
            )

            message_payload = {
                "contextId": context_id,
                "parts": [
                    {
                        "text": f"Search and hold top-rated hotel in {location} for checkin {checkin} to checkout {checkout} for {guests} guests."
                    }
                ],
            }

            response = None
            task_id = "task-hotel-shinjuku-99"

            if self.use_gateway:
                try:
                    from travel_concierge.gateway.client import send_gateway_message
                    gateway_res = send_gateway_message(
                        agent_name="hotel_booking_specialist",
                        payload=message_payload,
                        caller_spiffe_token=caller_spiffe_token,
                        target_token=target_token,
                        extra_headers=headers,
                    )
                    task_id = gateway_res.get("task_id") or gateway_res.get("taskId") or "task-hotel-shinjuku-99"
                    held_hotel = gateway_res.get("hotel")
                    response = MockAgentResponse(
                        text=f'{{"status": "held", "hotel": "{held_hotel.get("name") if held_hotel else "Hotel"}", "taskId": "{task_id}"}}',
                        usage_metadata=MockUsageMetadata(
                            prompt_token_count=gateway_res.get("metrics", {}).get("prompt_tokens", 1800),
                            cached_content_token_count=gateway_res.get("metrics", {}).get("cached_tokens", 1350),
                            candidates_token_count=gateway_res.get("metrics", {}).get("completion_tokens", 120),
                            total_token_count=gateway_res.get("metrics", {}).get("total_tokens", 1920),
                        ),
                        status="held",
                        data=gateway_res,
                    )
                except Exception as e:
                    logger.warning(f"Gateway hotel delegation fallback: {e}")
                    response = None

            if response is None:
                try:
                    if hasattr(self.agent, "send_message"):
                        response = self.agent.send_message(message=message_payload, headers=headers)
                except Exception as e:
                    logger.warning(f"Remote hotel A2A live call fallback: {e}")
                    response = None

            if response is None:
                hotel_data = MockHotelService.search_hotels(location, checkin, checkout, guests)
                held_hotel = hotel_data["hotels"][0]
                task_id = f"task-{held_hotel['hotel_id']}"

                response = MockAgentResponse(
                    text=f'{{"status": "held", "hotel": "{held_hotel["name"]}", "taskId": "{task_id}", "price_usd": {held_hotel["price_per_night_usd"]}}}',
                    usage_metadata=MockUsageMetadata(
                        prompt_token_count=1800,
                        cached_content_token_count=1350,
                        candidates_token_count=120,
                        total_token_count=1920,
                    ),
                    status="held",
                    data={"hotel": held_hotel, "taskId": task_id},
                )
            else:
                task_id = getattr(response, "data", {}).get("taskId", task_id) if hasattr(response, "data") and isinstance(response.data, dict) else task_id

            # Model Escalation evaluation
            from travel_concierge.agents.model_escalator import default_escalator
            prompt_str = message_payload["parts"][0]["text"]
            escalation_dec = default_escalator.evaluate_request(prompt_str, span=span, agent_name="hotel_subagent")

            logger.info(
                f"[hotel_subagent Context Management] Processing hotel hold for '{location}'. "
                f"Context technique: Extractive Compaction — holding best candidate and omitting raw search list. "
                f"Model Active: {escalation_dec.active_model}"
            )

            span.set_attribute("a2a.generated_task_id", task_id)
            metrics = track_llm_telemetry(response, span, agent_name="hotel_subagent", prompt_text=prompt_str)

            return {
                "task_id": task_id,
                "response": response,
                "metrics": metrics.to_dict() if metrics else None,
                "model_escalation": escalation_dec.to_dict(),
            }
