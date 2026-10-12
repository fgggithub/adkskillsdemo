"""
Unit tests for Restaurant, Hotel, Verification, and Root Orchestrator Agents.
"""
from travel_concierge.agents.restaurant_agent import RestaurantAgentWrapper, create_restaurant_subagent
from travel_concierge.agents.hotel_agent import HotelAgentWrapper, create_hotel_subagent
from travel_concierge.agents.verification_agent import VerificationAgentWrapper, create_verification_subagent
from travel_concierge.agents.root_agent import TravelConciergeRootAgent, create_travel_concierge_root_agent
from travel_concierge.tools.skill_registry import evaluate_dietary_compliance, GCPSkillRegistry


def test_dietary_advisor_skill():
    res_vegan = evaluate_dietary_compliance("Ain Soph Tokyo", "vegan")
    assert res_vegan["is_compliant"] is True

    res_steak = evaluate_dietary_compliance("Tokyo Wagyu House", "vegan")
    assert res_steak["is_compliant"] is False


def test_skill_registry_registration():
    registry = GCPSkillRegistry(project_id="test-proj")
    registry.register_skill("custom_advisor", evaluate_dietary_compliance)
    assert "custom_advisor" in registry.list_skills()
    assert registry.get_skill("custom_advisor") is not None


def test_restaurant_agent_wrapper_execution(valid_token_claims):
    wrapper = RestaurantAgentWrapper()
    result = wrapper.find_dining_options(
        context_id="ctx-test-1",
        query="vegan ramen in Tokyo",
        reference_task_ids=["task-hotel-1"],
        token_claims=valid_token_claims,
    )
    assert "response" in result
    assert "mcp_result" in result
    assert result["mcp_result"]["status"] == "success"
    assert result["metrics"]["prompt_tokens"] > 0


def test_hotel_agent_wrapper_execution():
    wrapper = HotelAgentWrapper()
    result = wrapper.search_and_hold_hotel(
        context_id="ctx-test-1",
        location="Tokyo Shinjuku",
    )
    assert result["task_id"].startswith("task-")
    assert result["response"].status == "held"
    assert result["metrics"]["cached_tokens"] > 0


def test_verification_agent_hitl_task_lifecycle():
    wrapper = VerificationAgentWrapper()
    result = wrapper.run_verification_task(
        context_id="ctx-test-1",
        reference_task_ids=["task-hotel-shinjuku-99"],
        user_auto_confirm=True,
    )
    assert result["state"] == "completed"
    assert result["interrupted"] is True
    assert "Please confirm authorization" in result["interrupt_message"]
    assert result["final_response"] is not None


def test_root_orchestrator_agent_end_to_end(valid_token_claims):
    root_agent = TravelConciergeRootAgent()
    trip_result = root_agent.plan_trip(
        destination="Kyoto Central",
        dining_query="traditional matcha & soba",
        context_id="ctx-kyoto-2026",
        token_claims=valid_token_claims,
        auto_confirm_booking=True,
    )

    assert trip_result["context_id"] == "ctx-kyoto-2026"
    assert trip_result["destination"] == "Kyoto Central"
    assert trip_result["hotel_booking"]["task_id"] is not None
    assert trip_result["restaurant_recommendations"]["mcp_result"]["status"] == "success"
    assert trip_result["verification"]["state"] == "completed"
    assert trip_result["telemetry"]["cache_hit_rate"] > 0.50
    assert trip_result["telemetry"]["cost_usd"] > 0.0
