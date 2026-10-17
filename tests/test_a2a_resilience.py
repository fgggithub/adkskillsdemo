"""
Unit tests for A2A Client Error capturing, HTTP 404 diagnosis, and fallback response delivery to root agent.
"""
import pytest
from unittest.mock import patch, MagicMock
from a2a.client.errors import A2AClientError
from google.adk.events import Event
from google.genai import types as genai_types

from travel_concierge.config import settings, _resolve_project_number
from travel_concierge.agents.base import ResilientRemoteA2aAgent
from google.adk.agents.remote_a2a_agent import RemoteA2aAgent
from travel_concierge.agents.restaurant_agent import (
    create_restaurant_subagent,
    RestaurantAgentWrapper,
)
from travel_concierge.agents.root_agent import TravelConciergeRootAgent
from travel_concierge.tools.mock_services import MockAgentResponse


def test_subagent_service_urls_resolution():
    """Verify that default Cloud Run service URLs use the dynamically resolved active project number."""
    active_project_num = _resolve_project_number()
    assert active_project_num
    assert "825245236792" not in settings.endpoints.restaurant_service_url
    assert "825245236792" not in settings.endpoints.hotel_service_url
    assert "825245236792" not in settings.endpoints.verification_service_url
    assert "825245236792" not in settings.endpoints.agent_gateway_url

    # Stale residual project number 318615323995 should not be in URLs if active is different
    if active_project_num != "318615323995":
        assert "318615323995" not in settings.endpoints.restaurant_service_url
        assert "318615323995" not in settings.endpoints.hotel_service_url
        assert "318615323995" not in settings.endpoints.verification_service_url
        assert "318615323995" not in settings.endpoints.agent_gateway_url

    assert active_project_num in settings.endpoints.restaurant_service_url
    assert active_project_num in settings.endpoints.hotel_service_url
    assert active_project_num in settings.endpoints.verification_service_url
    assert active_project_num in settings.endpoints.agent_gateway_url


def test_create_restaurant_subagent_resilient_type():
    """Verify factory returns ResilientRemoteA2aAgent."""
    agent = create_restaurant_subagent()
    assert isinstance(agent, ResilientRemoteA2aAgent)
    assert agent.name == "restaurant_booking_specialist"


def test_resilient_remote_a2a_agent_fallback_text():
    """Verify domain-specific fallback text generation."""
    agent = create_restaurant_subagent()
    text = agent._build_fallback_text("HTTP Error 404: Client error '404 Not Found'")
    assert "Restaurant booking" in text
    assert "404 Not Found" in text
    assert "Tokyo Vegan Izakaya" in text


@pytest.mark.asyncio
async def test_resilient_remote_a2a_agent_intercepts_error_event():
    """Verify _run_async_impl intercepts error events without content and populates fallback text."""
    agent = create_restaurant_subagent()

    async def mock_super_run(ctx):
        yield Event(
            author="restaurant_booking_specialist",
            error_message="A2A request failed: A2AClientError: HTTP Error 404: Client error '404 Not Found'",
            invocation_id="inv-123",
            branch="main",
            custom_metadata={"a2a:error": "404 Not Found"},
        )

    mock_ctx = MagicMock()
    mock_ctx.invocation_id = "inv-123"
    mock_ctx.branch = "main"

    with patch.object(ResilientRemoteA2aAgent.__bases__[0], "_run_async_impl", side_effect=mock_super_run):
        events = [event async for event in agent._run_async_impl(mock_ctx)]

    assert len(events) == 1
    event = events[0]
    assert event.content is not None
    assert len(event.content.parts) > 0
    assert "Tokyo Vegan Izakaya" in event.content.parts[0].text
    assert event.output is not None


@pytest.mark.asyncio
async def test_resilient_remote_a2a_agent_catches_unhandled_exception():
    """Verify _run_async_impl catches unhandled A2AClientError and yields fallback Event."""
    agent = create_restaurant_subagent()

    async def mock_failing_run(ctx):
        raise A2AClientError("HTTP Error 404: Client error '404 Not Found' for url 'https://restaurant-booking-specialist-825245236792.us-central1.run.app'")
        yield Event(author="never_reached")

    mock_ctx = MagicMock()
    mock_ctx.invocation_id = "inv-456"
    mock_ctx.branch = "main"

    with patch.object(ResilientRemoteA2aAgent.__bases__[0], "_run_async_impl", side_effect=mock_failing_run):
        events = [event async for event in agent._run_async_impl(mock_ctx)]

    assert len(events) == 1
    event = events[0]
    assert event.author == "restaurant_booking_specialist"
    assert event.content is not None
    assert "Tokyo Vegan Izakaya" in event.content.parts[0].text
    assert event.custom_metadata.get("fallback_applied") == "true"


def test_restaurant_wrapper_captures_a2a_404_error(valid_token_claims):
    """Verify RestaurantAgentWrapper captures 404 A2AClientError and returns response to root agent."""
    mock_subagent = MagicMock()
    mock_subagent.name = "restaurant_booking_specialist"
    mock_subagent.send_message.side_effect = A2AClientError(
        "HTTP Error 404: Client error '404 Not Found' for url 'https://restaurant-booking-specialist-825245236792.us-central1.run.app'"
    )

    wrapper = RestaurantAgentWrapper(agent=mock_subagent, use_gateway=False)

    result = wrapper.find_dining_options(
        context_id="ctx-test-404",
        query="vegan ramen in Tokyo",
        reference_task_ids=["task-hotel-1"],
        token_claims=valid_token_claims,
    )

    assert "response" in result
    assert result["response"] is not None
    assert result["status"] == "degraded"
    assert "recommendations" in result["response"].text
    assert "metrics" in result
    assert result["metrics"]["total_tokens"] > 0


def test_root_agent_plan_trip_with_restaurant_404_exception(valid_token_claims):
    """Verify TravelConciergeRootAgent handles restaurant subagent 404 without crashing."""
    mock_restaurant = MagicMock()
    mock_restaurant.find_dining_options.side_effect = A2AClientError(
        "HTTP Error 404: Client error '404 Not Found' for url 'https://restaurant-booking-specialist-825245236792.us-central1.run.app'"
    )

    root_agent = TravelConciergeRootAgent(restaurant_wrapper=mock_restaurant)

    trip_result = root_agent.plan_trip(
        destination="Tokyo Ginza",
        dining_query="vegan dining",
        context_id="ctx-root-404-test",
        token_claims=valid_token_claims,
        auto_confirm_booking=True,
    )

    assert trip_result["context_id"] == "ctx-root-404-test"
    assert trip_result["hotel_booking"]["task_id"] is not None
    assert "restaurant_recommendations" in trip_result
    restaurant_rec = trip_result["restaurant_recommendations"]
    assert restaurant_rec["response"] is not None
    assert restaurant_rec["response"].status == "degraded"
    assert "Default verified dining recommendations" in restaurant_rec["response"].text
    assert trip_result["verification"]["state"] == "completed"
    assert trip_result["telemetry"]["cost_usd"] > 0.0


@pytest.mark.asyncio
async def test_resilient_agent_handles_event_loop_closed_exception():
    """Verify ResilientRemoteA2aAgent catches RuntimeError: Event loop is closed and yields fallback."""
    agent = ResilientRemoteA2aAgent(
        name="restaurant_booking_specialist",
        agent_card="https://fake-service.run.app/.well-known/agent-card.json",
    )

    with patch.object(
        RemoteA2aAgent,
        "_run_async_impl",
        side_effect=RuntimeError("Event loop is closed"),
    ):
        ctx = MagicMock()
        ctx.invocation_id = "inv-loop-test"
        ctx.branch = "main"

        events = [e async for e in agent._run_async_impl(ctx)]
        assert len(events) == 1
        fallback_event = events[0]
        assert "restaurant" in fallback_event.content.parts[0].text.lower()
        assert "communication issue" in fallback_event.content.parts[0].text
        assert fallback_event.custom_metadata["fallback_applied"] == "true"
        assert "Event loop is closed" in fallback_event.custom_metadata["a2a_intercepted_error"]


def test_resilient_agent_send_message_handles_event_loop_closed():
    """Verify ResilientRemoteA2aAgent.send_message handles RuntimeError: Event loop is closed."""
    agent = ResilientRemoteA2aAgent(
        name="restaurant_booking_specialist",
        agent_card="https://fake-service.run.app/.well-known/agent-card.json",
    )
    agent._target_url = "https://fake-service.run.app"

    with patch("httpx.Client.post", side_effect=RuntimeError("Event loop is closed")):
        resp = agent.send_message({"query": "sushi"})
        assert resp is not None
        assert resp.status == "degraded"
        assert "Event loop is closed" in resp.data["error"]
        assert "fallback" in resp.data

