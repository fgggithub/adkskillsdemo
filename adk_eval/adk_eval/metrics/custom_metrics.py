"""
ADK Custom Metrics for Travel Concierge Multi-Agent Evaluation.
Provides deterministic, heuristic, and policy verification metrics conforming
to the Google ADK Evaluation framework.
"""
from typing import Dict, Any, List, Optional
import re


def evaluate_intent_routing(instance: Dict[str, Any]) -> Dict[str, Any]:
    """
    Evaluates whether the root orchestrator correctly delegated to the expected sub-agent
    (e.g., hotel_booking_specialist or restaurant_booking_specialist) based on user query intent.
    """
    expected_target = instance.get("expected_target_agent") or instance.get("expected_agent", "hotel_booking_specialist")
    agent_data = instance.get("agent_data") or {}
    tool_uses = instance.get("tool_uses") or []
    
    # Check turns / events if agent_data is present
    if "turns" in agent_data:
        for turn in agent_data.get("turns", []):
            for event in turn.get("events", []):
                for part in (event.get("content") or {}).get("parts", []):
                    if "function_call" in part:
                        tool_uses.append(part["function_call"])

    # Look for matching tool invocation or subagent routing in result
    actual_tools = [t.get("name", "") if isinstance(t, dict) else getattr(t, "name", "") for t in tool_uses]
    actual_agent = instance.get("routed_agent") or instance.get("target_agent", "")

    if not actual_agent and "hotel" in expected_target.lower():
        if any("hotel" in t.lower() or "hold" in t.lower() for t in actual_tools):
            actual_agent = "hotel_booking_specialist"
    elif not actual_agent and "restaurant" in expected_target.lower():
        if any("restaurant" in t.lower() or "dining" in t.lower() or "zomato" in t.lower() for t in actual_tools):
            actual_agent = "restaurant_booking_specialist"

    routed_correctly = (expected_target.lower() in actual_agent.lower()) or (actual_agent.lower() in expected_target.lower())
    score = 1.0 if routed_correctly else 0.0

    return {
        "score": score,
        "explanation": f"Expected agent '{expected_target}', routed to '{actual_agent or actual_tools}'."
    }


def evaluate_task_propagation(instance: Dict[str, Any]) -> Dict[str, Any]:
    """
    Evaluates whether reference task IDs (e.g., hotel hold task IDs) were properly propagated
    across downstream sub-agents (restaurant search, verification agent).
    """
    expected_task_id = instance.get("expected_task_id")
    received_task_ids = instance.get("received_task_ids") or []
    agent_response = str(instance.get("response") or instance.get("agent_response", ""))

    if expected_task_id:
        if expected_task_id in received_task_ids or expected_task_id in agent_response:
            return {"score": 1.0, "explanation": f"Task ID '{expected_task_id}' successfully propagated."}
        return {"score": 0.0, "explanation": f"Task ID '{expected_task_id}' missing from downstream context."}

    # If verifying format of task IDs (e.g. task-hotel-...)
    if any(t.startswith("task-") for t in received_task_ids) or "task-" in agent_response:
        return {"score": 1.0, "explanation": "Valid reference task ID found in invocation context."}

    return {"score": 0.0, "explanation": "No valid reference task ID found."}


def evaluate_guardrail_compliance(instance: Dict[str, Any]) -> Dict[str, Any]:
    """
    Evaluates response against length guardrails, stop sequences, and conciseness rules.
    """
    response_text = str(instance.get("response") or instance.get("final_response") or "")
    max_tokens = instance.get("max_tokens", 1000)

    # Word count heuristic for token length estimate
    est_tokens = len(response_text.split()) * 1.3
    if est_tokens > max_tokens:
        return {
            "score": 0.0,
            "explanation": f"Response exceeded token budget ({est_tokens:.0f} > {max_tokens})."
        }

    # Guardrail against boilerplate filler
    filler_phrases = ["as an ai", "i hope this helps", "feel free to ask", "have a nice day"]
    found_fillers = [f for f in filler_phrases if f in response_text.lower()]
    if found_fillers:
        return {
            "score": 0.5,
            "explanation": f"Response contains unnecessary conversational fillers: {found_fillers}."
        }

    return {"score": 1.0, "explanation": "Response complies with enterprise conciseness guardrails."}


def evaluate_cache_efficiency(instance: Dict[str, Any]) -> Dict[str, Any]:
    """
    Evaluates whether context cache hit rate meets or exceeds the target threshold (e.g., 50%).
    """
    telemetry = instance.get("telemetry") or instance.get("metrics") or {}
    cache_hit_rate = telemetry.get("cache_hit_rate", 0.0)
    cached_tokens = telemetry.get("cached_tokens", 0)
    total_prompt_tokens = telemetry.get("prompt_tokens", 0)

    if total_prompt_tokens > 0 and cache_hit_rate == 0.0:
        cache_hit_rate = cached_tokens / total_prompt_tokens

    target_hit_rate = instance.get("target_cache_hit_rate", 0.50)
    score = 1.0 if cache_hit_rate >= target_hit_rate else (cache_hit_rate / target_hit_rate if target_hit_rate > 0 else 1.0)
    score = min(1.0, max(0.0, score))

    return {
        "score": score,
        "explanation": f"Cache hit rate is {cache_hit_rate:.1%} (target: {target_hit_rate:.1%}, cached tokens: {cached_tokens})."
    }


def evaluate_security_enforcement(instance: Dict[str, Any]) -> Dict[str, Any]:
    """
    Evaluates authorization policy enforcement and graceful 403 Forbidden handling.
    """
    token_claims = instance.get("token_claims") or {}
    user_groups = token_claims.get("groups", [])
    expected_status = instance.get("expected_status", 200)
    actual_status = instance.get("status_code", 200)
    is_error = instance.get("is_error", False)
    response_text = str(instance.get("response") or instance.get("error", ""))

    # Unauthorized access check
    if "MCPUSERS" not in user_groups or expected_status == 403:
        if actual_status == 403 or "403" in response_text or "forbidden" in response_text.lower() or is_error:
            return {
                "score": 1.0,
                "explanation": "Security guardrail properly blocked unauthorized caller with 403 Forbidden."
            }
        return {
            "score": 0.0,
            "explanation": "Security violation: Unauthorized caller was granted access without 403 check."
        }

    # Authorized access check
    if actual_status == 200 and not is_error:
        return {
            "score": 1.0,
            "explanation": "Authorized request executed successfully."
        }

    return {
        "score": 0.5,
        "explanation": f"Authorized request encountered unexpected status {actual_status}."
    }


def evaluate_dietary_adherence(instance: Dict[str, Any]) -> Dict[str, Any]:
    """
    Evaluates whether the recommended restaurants adhere strictly to dietary restrictions (e.g. vegan).
    """
    dietary_pref = instance.get("dietary_preference", "vegan").lower()
    recommendations = instance.get("recommendations") or []
    response_text = str(instance.get("response") or "")

    non_compliant_keywords = {
        "vegan": ["beef", "steak", "wagyu", "pork", "chicken", "bacon", "cheese fondue"],
        "halal": ["pork", "bacon", "alcohol", "wine"],
        "gluten_free": ["wheat bread", "regular pasta", "flour tortilla"],
    }

    prohibited = non_compliant_keywords.get(dietary_pref, [])
    found_violations = [p for p in prohibited if p in response_text.lower()]

    if found_violations:
        return {
            "score": 0.0,
            "explanation": f"Dietary violation: Found non-{dietary_pref} items ({found_violations}) in recommendations."
        }

    return {
        "score": 1.0,
        "explanation": f"All recommendations adhere to {dietary_pref} dietary requirements."
    }
