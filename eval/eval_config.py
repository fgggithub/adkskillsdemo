"""
Evaluation datasets and benchmark scenario definitions.
"""
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional


@dataclass
class EvalTestCase:
    id: str
    name: str
    category: str  # "intent_routing", "task_propagation", "guardrails", "resilience", "cache_efficiency", "security"
    destination: str
    dining_query: str
    token_claims: Dict[str, Any]
    expected_subagents: List[str]
    expected_hotel_task_prefix: str
    requires_hitl: bool
    expected_status: str
    min_cache_hit_rate: float
    description: str


EVAL_DATASET: List[EvalTestCase] = [
    EvalTestCase(
        id="eval-001",
        name="Standard Tokyo Vegan Trip",
        category="intent_routing",
        destination="Tokyo Shinjuku",
        dining_query="vegan ramen options",
        token_claims={
            "sub": "user:eval1@corp.example",
            "groups": ["MCPUSERS", "TRAVELERS"],
            "scope": "https://mcp-server.zomato.com/scopes/restaurants.read",
        },
        expected_subagents=["hotel_booking_specialist", "restaurant_booking_specialist", "final_verification_agent"],
        expected_hotel_task_prefix="task-hotel-",
        requires_hitl=True,
        expected_status="completed",
        min_cache_hit_rate=0.60,
        description="Verifies end-to-end multi-agent orchestration and HITL verification.",
    ),
    EvalTestCase(
        id="eval-002",
        name="Kyoto Organic Dining",
        category="task_propagation",
        destination="Kyoto Central",
        dining_query="organic matcha and kaiseki",
        token_claims={
            "sub": "user:eval2@corp.example",
            "groups": ["MCPUSERS", "TRAVELERS"],
            "scope": "https://mcp-server.zomato.com/scopes/restaurants.read",
        },
        expected_subagents=["hotel_booking_specialist", "restaurant_booking_specialist"],
        expected_hotel_task_prefix="task-hotel-",
        requires_hitl=True,
        expected_status="completed",
        min_cache_hit_rate=0.50,
        description="Verifies accurate reference task ID propagation from Hotel to Restaurant Agent.",
    ),
    EvalTestCase(
        id="eval-003",
        name="Unauthorized Group Request",
        category="security",
        destination="Osaka Namba",
        dining_query="street food takoyaki",
        token_claims={
            "sub": "user:unauthorized@corp.example",
            "groups": ["GUEST_ONLY"],
            "scope": "https://mcp-server.zomato.com/scopes/restaurants.read",
        },
        expected_subagents=[],
        expected_hotel_task_prefix="",
        requires_hitl=False,
        expected_status="forbidden",
        min_cache_hit_rate=0.0,
        description="Verifies IAM group policy enforcement blocks unauthorized MCP calls with 403 Forbidden.",
    ),
    EvalTestCase(
        id="eval-004",
        name="Missing OAuth Scope Request",
        category="security",
        destination="Sapporo Susukino",
        dining_query="miso ramen",
        token_claims={
            "sub": "user:eval4@corp.example",
            "groups": ["MCPUSERS"],
            "scope": "https://other.com/read",
        },
        expected_subagents=[],
        expected_hotel_task_prefix="",
        requires_hitl=False,
        expected_status="forbidden",
        min_cache_hit_rate=0.0,
        description="Verifies OAuth 2.0 scope validation rejects tokens lacking restaurants.read scope.",
    ),
    EvalTestCase(
        id="eval-005",
        name="High Token Cache Reusability",
        category="cache_efficiency",
        destination="Fukuoka Hakata",
        dining_query="tonkotsu alternative plant broth",
        token_claims={
            "sub": "user:eval5@corp.example",
            "groups": ["MCPUSERS", "TRAVELERS"],
            "scope": "https://mcp-server.zomato.com/scopes/restaurants.read",
        },
        expected_subagents=["hotel_booking_specialist", "restaurant_booking_specialist"],
        expected_hotel_task_prefix="task-hotel-",
        requires_hitl=True,
        expected_status="completed",
        min_cache_hit_rate=0.70,
        description="Verifies that Context Cache achieves >70% hit rate on prompt tokens for large system prompts.",
    ),
]
