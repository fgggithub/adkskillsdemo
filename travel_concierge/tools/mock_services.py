"""
Mock services and test fixtures for A2A Subagents, MCP tools, and HITL Tasks.
"""
from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional, Iterator


@dataclass
class MockTaskStatus:
    state: str  # e.g., 'input-required', 'running', 'completed', 'failed'
    message: str


@dataclass
class MockTaskEvent:
    task_id: str
    task_status: Optional[MockTaskStatus] = None
    task_artifact: Optional[Dict[str, Any]] = None


@dataclass
class MockUsageMetadata:
    prompt_token_count: int = 2400
    cached_content_token_count: int = 1800
    candidates_token_count: int = 150
    total_token_count: int = 2550


@dataclass
class MockAgentResponse:
    text: str
    usage_metadata: MockUsageMetadata = field(default_factory=MockUsageMetadata)
    status: str = "success"
    data: Optional[Dict[str, Any]] = None

    def __str__(self):
        return self.text


class MockHotelService:
    """Simulates remote Hotel Booking Specialist A2A agent."""

    @staticmethod
    def get_agent_card() -> Dict[str, Any]:
        return {
            "name": "hotel_booking_specialist",
            "version": "2.0.0",
            "description": "Remote A2A Agent for finding and reserving accommodations.",
            "capabilities": {
                "streaming": True,
                "push_notifications": True,
                "task_lifecycle": True,
            },
            "endpoints": {
                "message": "/v1/message",
                "streaming": "/v1/message/stream",
            },
        }

    @staticmethod
    def search_hotels(location: str, checkin: str, checkout: str, guests: int = 1) -> Dict[str, Any]:
        return {
            "status": "success",
            "location": location,
            "hotels": [
                {
                    "hotel_id": "hotel-shinjuku-99",
                    "name": "Park Hyatt Tokyo (Shinjuku)",
                    "price_per_night_usd": 420.0,
                    "rating": 4.9,
                    "available_rooms": ["Deluxe King", "Executive Suite"],
                },
                {
                    "hotel_id": "hotel-shibuya-101",
                    "name": "Cerulean Tower Tokyu Hotel",
                    "price_per_night_usd": 280.0,
                    "rating": 4.7,
                    "available_rooms": ["Standard Twin", "Corner King"],
                },
            ],
        }


class MockZomatoService:
    """Simulates remote Zomato MCP Server responses."""

    @staticmethod
    def search_restaurants(query: str, location: str = "Tokyo") -> Dict[str, Any]:
        return {
            "status": "success",
            "query": query,
            "location": location,
            "restaurants": [
                {
                    "id": "rest-vegan-tokyo-1",
                    "name": "Ain Soph. Journey Shinjuku",
                    "cuisine": "Vegan / Plant-based Desserts & Dining",
                    "rating": 4.8,
                    "address": "3-8-9 Shinjuku, Tokyo",
                },
                {
                    "id": "rest-ramen-tokyo-2",
                    "name": "T's Tantan Tokyo",
                    "cuisine": "Vegan Ramen",
                    "rating": 4.7,
                    "address": "Marunouchi, Chiyoda-ku, Tokyo",
                },
            ],
        }


class MockVerificationService:
    """Simulates async Human-in-the-Loop Verification Subagent with Task Lifecycle."""

    @staticmethod
    def simulate_task_stream(task_id: str = "task-hotel-shinjuku-99") -> Iterator[MockTaskEvent]:
        yield MockTaskEvent(
            task_id=task_id,
            task_status=MockTaskStatus(
                state="running",
                message="Initializing payment gateway and validating reservation hold...",
            ),
        )
        yield MockTaskEvent(
            task_id=task_id,
            task_status=MockTaskStatus(
                state="input-required",
                message="Please confirm authorization to charge $420.00 to card ending in 4242 for Shinjuku stay.",
            ),
        )

    @staticmethod
    def resume_task(task_id: str, user_confirmation: str) -> MockAgentResponse:
        return MockAgentResponse(
            text=f"Task {task_id} confirmed and finalized. Booking reference: CONF-TOK-88991.",
            usage_metadata=MockUsageMetadata(
                prompt_token_count=1200,
                cached_content_token_count=900,
                candidates_token_count=80,
                total_token_count=1280,
            ),
            status="completed",
            data={
                "task_id": task_id,
                "confirmation_code": "CONF-TOK-88991",
                "user_confirmation": user_confirmation,
            },
        )
