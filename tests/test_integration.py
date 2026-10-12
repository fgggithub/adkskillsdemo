"""
Integration tests for FastAPI endpoints and server orchestration.
"""
import pytest
from fastapi.testclient import TestClient
from travel_concierge.server import app

client = TestClient(app)


def test_healthz_endpoint():
    response = client.get("/healthz")
    assert response.status_code == 200
    assert response.json()["status"] == "healthy"
    assert response.json()["service"] == "travel_concierge"


def test_agent_card_discovery_endpoint():
    response = client.get("/.well-known/agent-card.json")
    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "travel_concierge_2.0"
    assert "subagents" in data["capabilities"]
    assert "hotel_booking_specialist" in data["capabilities"]["subagents"]


def test_plan_trip_api_endpoint():
    payload = {
        "destination": "Tokyo Shinjuku",
        "dining_query": "vegan ramen",
        "context_id": "ctx-api-test-01",
        "auto_confirm": True,
        "token_claims": {
            "sub": "user:test_api@example.com",
            "groups": ["MCPUSERS", "TRAVELERS"],
            "scope": "https://mcp-server.zomato.com/scopes/restaurants.read",
        },
    }
    response = client.post("/v1/trips/plan", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    assert data["destination"] == "Tokyo Shinjuku"
    assert "telemetry" in data
    assert data["telemetry"]["cost_usd"] > 0.0


def test_plan_trip_api_unauthorized():
    payload = {
        "destination": "Tokyo Shinjuku",
        "dining_query": "vegan ramen",
        "token_claims": {
            "sub": "user:unauthorized@example.com",
            "groups": ["GUEST_ONLY"],
            "scope": "https://mcp-server.zomato.com/scopes/restaurants.read",
        },
    }
    response = client.post("/v1/trips/plan", json=payload)
    assert response.status_code == 403


def test_webhook_push_endpoint():
    payload = {
        "event_type": "task_status_changed",
        "task_id": "task-hotel-shinjuku-99",
        "status": "completed",
        "payload": {"booking_id": "BK-1234"},
    }
    response = client.post("/a2a/webhooks/push", json=payload)
    assert response.status_code == 200
    assert response.json()["status"] == "acknowledged"
    assert response.json()["task_id"] == "task-hotel-shinjuku-99"
