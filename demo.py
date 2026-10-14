"""
MCP using GcpAuthProvider extended with enterprise skills dynamically loaded via GCPSkillRegistry,
featuring a Circuit Breaker pattern, IAM group validation, OpenTelemetry tracing with
Explicit Context Cache Hit Rate tracking, Token Caching, and Generation Guardrails 
(Max Output Tokens, Stop Sequences, Thinking Level, and Output Reduction Instructions).
"""
import os
import time
import socket
import threading
import ipaddress
from typing import Callable, Any, Dict, List
from urllib.parse import urlparse

from google import genai
from google.genai import types

from google.adk.agents import Agent
from google.adk.agents.remote_a2a_agent import RemoteA2aAgent, AGENT_CARD_WELL_KNOWN_PATH
from google.adk.tools.mcp_tool import McpToolset
from google.adk.tools.mcp_tool.mcp_session_manager import StreamableHTTPConnectionParams
from travel_concierge.tools.mcp_toolset import GcpAuthProviderScheme
from travel_concierge.tools.skill_registry import GCPSkillRegistry, SkillToolset

from opentelemetry import trace
from opentelemetry.propagate import inject
from travel_concierge.telemetry.tracer import init_tracer, flush_tracer

# ==============================================================================
# 1. OpenTelemetry Initialization & Pricing Constants
# ==============================================================================
tracer = init_tracer("travel_concierge_demo")

# Token Pricing Constants (Gemini 2.5 Flash)
INPUT_PRICE_PER_1M = 0.30
CACHED_INPUT_PRICE_PER_1M = 0.075  # 75% discount on cached prompt tokens
OUTPUT_PRICE_PER_1M = 2.50


# ==============================================================================
# 2. Context Caching Manager
# ==============================================================================
class ExplicitContextCacheManager:
    """Manages creation and retrieval of Vertex AI / Gemini Explicit Cached Content."""

    def __init__(self, project_id: str, location: str = "us-central1"):
        self.client = genai.Client(vertexai=True, project=project_id, location=location)

    def create_agent_context_cache(
        self,
        model: str,
        system_instruction: str,
        ttl_minutes: int = 60,
        display_name: str = "travel_concierge_shared_context"
    ) -> types.CachedContent:
        """
        Creates an explicit cached content object for shared agent instructions,
        system context, and tools schema.
        """
        try:
            cache = self.client.caches.create(
                model=model,
                config=types.CreateCachedContentConfig(
                    display_name=display_name,
                    contents=[system_instruction],
                    ttl=f"{ttl_minutes * 60}s"
                )
            )
            print(f"[Context Cache] Created Cache ID: {cache.name} (Expires: {cache.expire_time})")
            return cache
        except Exception as e:
            print(f"[Context Cache] Fallback mock cache (API returned: {e})")
            class MockCachedContent:
                name = "cachedContents/mock-travel-concierge-shared-context"
                expire_time = "2026-10-14T00:00:00Z"
            return MockCachedContent()


# Initialize Cache Manager
gcp_project = os.environ.get("GOOGLE_CLOUD_PROJECT", "my-gcp-project")
cache_manager = ExplicitContextCacheManager(project_id=gcp_project)


# ==============================================================================
# 3. Circuit Breaker for MCP Resilience
# ==============================================================================
class CircuitBreakerOpenException(Exception):
    """Raised when the circuit breaker is OPEN and short-circuiting calls."""
    pass


class MCPCircuitBreaker:
    def __init__(self, failure_threshold: int = 3, recovery_timeout: float = 30.0, execution_timeout: float = 5.0):
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.execution_timeout = execution_timeout
        self.failure_count = 0
        self.state = "CLOSED"
        self.last_state_change = time.time()
        self._lock = threading.Lock()

    def __call__(self, func: Callable):
        def wrapper(*args, **kwargs):
            with self._lock:
                now = time.time()
                if self.state == "OPEN":
                    if now - self.last_state_change > self.recovery_timeout:
                        self.state = "HALF-OPEN"
                    else:
                        raise CircuitBreakerOpenException(
                            "Circuit Breaker is OPEN. Tool call blocked to protect service."
                        )

            try:
                start_time = time.time()
                result = func(*args, **kwargs)
                duration = time.time() - start_time

                if duration > self.execution_timeout:
                    raise TimeoutError(f"MCP tool execution exceeded threshold ({duration:.2f}s > {self.execution_timeout}s)")

                if result is None or (isinstance(result, dict) and not result.get("results")):
                    raise ValueError("MCP tool returned null or empty result payload.")

                with self._lock:
                    if self.state in ("HALF-OPEN", "OPEN"):
                        self.state = "CLOSED"
                        self.failure_count = 0
                return result

            except Exception as e:
                with self._lock:
                    self.failure_count += 1
                    if self.failure_count >= self.failure_threshold:
                        self.state = "OPEN"
                        self.last_state_change = time.time()
                
                return {
                    "status": "degraded_fallback",
                    "error": str(e),
                    "circuit_state": self.state,
                    "results": ["Cached/Default dining options near hotel"]
                }
        return wrapper


zomato_circuit_breaker = MCPCircuitBreaker(failure_threshold=3, recovery_timeout=15.0, execution_timeout=3.0)


# ==============================================================================
# 4. Auth Decorators & Helpers
# ==============================================================================
def require_mcp_group_membership(required_group: str = "MCPUSERS"):
    def decorator(func):
        def wrapper(token_claims: dict, *args, **kwargs):
            user_groups = token_claims.get("groups", [])
            if required_group not in user_groups:
                raise PermissionError(f"403 Forbidden: User not in group '{required_group}'.")
            return func(token_claims, *args, **kwargs)
        return wrapper
    return decorator


def require_oauth_scope(required_scope: str):
    def decorator(func):
        def wrapper(token_claims: dict, *args, **kwargs):
            granted_scopes = token_claims.get("scope", "").split(" ")
            if required_scope not in granted_scopes:
                raise PermissionError(f"403 Forbidden: Missing scope '{required_scope}'.")
            return func(token_claims, *args, **kwargs)
        return wrapper
    return decorator

@require_mcp_group_membership("MCPUSERS")
@require_oauth_scope("https://mcp-server.zomato.com/scopes/restaurants.read")
@zomato_circuit_breaker

def execute_zomato_search(token_claims: dict, query: str):
    return {"status": "success", "results": [f"Found restaurants for query: {query}"]}


from travel_concierge.security.ssrf_validator import is_safe_webhook_url


# ==============================================================================
# 5. Skill Registry & Sub-Agents Initialization
# ==============================================================================
skill_registry = GCPSkillRegistry(project_id=gcp_project, location="us-central1")
registry_skill_toolset = SkillToolset(skills=[], registry=skill_registry)

zomato_mcp_toolset = McpToolset(
    connection_params=StreamableHTTPConnectionParams(
        url="https://mcp-server.zomato.com/mcp",
        auth_scheme=GcpAuthProviderScheme(audience="https://mcp-server.zomato.com/mcp")
    ),
    tool_filter=["search_restaurants", "get_restaurant_details", "get_restaurant_reviews", "search_by_cuisine"]
)

# Explicit system prompt optimizations for token reduction
SHARED_SYSTEM_INSTRUCTION = """
You are an enterprise travel dining and hotel concierge agent.
Operational Guidelines:
1. Load validation workflows dynamically from GCPSkillRegistry.
2. Search available registry skills (like 'dietary_advisor') to filter dining options.
3. If tool execution returns a 403 Forbidden error or a 'degraded_fallback' status, clearly explain the access limitation or present cached default options.
4. Pass reference task IDs accurately between hotel and restaurant booking agents.

Formatting & Output Efficiency Guardrails:
- Be extremely concise. Avoid preambles, conversational filler, conversational greetings, or concluding remarks.
- Deliver requested structured information immediately.
"""

# Create Context Cache for the Orchestrator / Sub-Agent System Instructions
shared_cached_content = cache_manager.create_agent_context_cache(
    model="gemini-2.5-flash",
    system_instruction=SHARED_SYSTEM_INSTRUCTION,
    ttl_minutes=60,
    display_name="travel_concierge_base_cache"
)

# Generation config controlling output shape, stop sequences, token limits, and thinking depth
AGENT_GENERATION_CONFIG = types.GenerateContentConfig(
    max_output_tokens=1000,                           # Cap maximum response output tokens
    stop_sequences=["END_OF_CONCIERGE_RESPONSE", "### END"], # Prevent agent runaway generation
    response_mime_type="application/json",             # Enforce structured output schema
    cached_content=shared_cached_content.name,
    thinking_config=types.ThinkingConfig(
        thinking_budget=2048,                        # Sets maximum reasoning/thinking token allocation
        thinking_level="LOW"                          # Options: "LOW" (fast/cheaper reasoning) or "HIGH" (deep reasoning)
    )
)

# Agent setup referencing cached content + constrained generation config
restaurant_subagent = Agent(
    name="restaurant_booking_specialist",
    model="gemini-2.5-flash",
    description="Handles searching restaurants and dining options via Zomato MCP.",
    instruction=SHARED_SYSTEM_INSTRUCTION,
    tools=[zomato_mcp_toolset, registry_skill_toolset],
    generate_content_config=AGENT_GENERATION_CONFIG,
)

class MockUsageMetadata:
    prompt_token_count = 1200
    cached_content_token_count = 900
    candidates_token_count = 150
    total_token_count = 1350

class MockAgentResponse:
    usage_metadata = MockUsageMetadata()
    text = "Found vegan dining: Ain Soph. Journey Shinjuku, Nagi Vegan Ramen."

object.__setattr__(restaurant_subagent, "send_message", lambda message, headers=None: MockAgentResponse())


WEBHOOK_CALLBACK_URL = "https://travel-concierge.example.com/a2a/webhooks/push"
if not is_safe_webhook_url(WEBHOOK_CALLBACK_URL):
    raise ValueError(f"Blocked unsafe webhook URL: {WEBHOOK_CALLBACK_URL}")

hotel_subagent = RemoteA2aAgent(
    name="hotel_booking_specialist",
    description="Handles finding and booking hotel accommodations on remote cloud service.",
    agent_card=f"https://hotel-booking-service.partner-cloud.com{AGENT_CARD_WELL_KNOWN_PATH}",
    use_legacy=False,
)
setattr(hotel_subagent, "_push_notification_config", {"url": WEBHOOK_CALLBACK_URL, "token": "signed-jwt-or-opaque-auth-token"})

travel_concierge = Agent(
    name="travel_concierge_2_0",
    model="gemini-2.5-flash",
    instruction=SHARED_SYSTEM_INSTRUCTION,
    tools=[registry_skill_toolset],
    sub_agents=[hotel_subagent, restaurant_subagent],
    generate_content_config=AGENT_GENERATION_CONFIG,
)


# ==============================================================================
# 6. Pipeline Execution with Hit Rate Metrics & Cost Tracking
# ==============================================================================
def run_travel_trip_pipeline():
    TRIP_CONTEXT_ID = "ctx-tokyo-trip-2026"
    valid_token_claims = {
        "sub": "user:alice@example.com",
        "groups": ["MCPUSERS", "TRAVELERS"],
        "scope": "https://mcp-server.zomato.com/scopes/restaurants.read"
    }

    print("--- Authorized Call Simulation ---")
    res = execute_zomato_search(valid_token_claims, "Shinjuku Ramen")
    print(f"Tool Execution Output: {res}")

    with tracer.start_as_current_span("orchestrate_trip_planning") as root_span:
        root_span.set_attribute("a2a.context_id", TRIP_CONTEXT_ID)

        with tracer.start_as_current_span("delegate_restaurant_agent") as rest_span:
            restaurant_headers = {}
            inject(restaurant_headers)

            response = restaurant_subagent.send_message(
                message={
                    "contextId": TRIP_CONTEXT_ID,
                    "referenceTaskIds": ["task-hotel-shinjuku-99"],
                    "parts": [{"text": "Find vegan dinner options near the hotel."}]
                },
                headers=restaurant_headers
            )

            # Extract token usage metadata and calculate cache hit rate
            usage = getattr(response, "usage_metadata", None)
            if usage:
                prompt_tokens = getattr(usage, "prompt_token_count", 0)
                cached_tokens = getattr(usage, "cached_content_token_count", 0)
                completion_tokens = getattr(usage, "candidates_token_count", 0)
                total_tokens = getattr(usage, "total_token_count", 0)

                # Calculate Context Cache Hit Rate: cachedContentTokenCount / promptTokenCount
                cache_hit_rate = (cached_tokens / prompt_tokens) if prompt_tokens > 0 else 0.0

                # Non-cached prompt tokens = Total Prompt Tokens - Cached Tokens
                uncached_prompt_tokens = max(0, prompt_tokens - cached_tokens)

                # Compute operational cost with explicit cache discount
                cost = ((uncached_prompt_tokens / 1_000_000) * INPUT_PRICE_PER_1M) + \
                       ((cached_tokens / 1_000_000) * CACHED_INPUT_PRICE_PER_1M) + \
                       ((completion_tokens / 1_000_000) * OUTPUT_PRICE_PER_1M)

                # Record metrics onto OpenTelemetry span
                rest_span.set_attribute("llm.usage.prompt_tokens", prompt_tokens)
                rest_span.set_attribute("llm.usage.cached_tokens", cached_tokens)
                rest_span.set_attribute("llm.usage.completion_tokens", completion_tokens)
                rest_span.set_attribute("llm.usage.total_tokens", total_tokens)
                rest_span.set_attribute("llm.usage.cache_hit_rate", cache_hit_rate)
                rest_span.set_attribute("llm.usage.cost_usd", cost)

                if cache_hit_rate < 0.50 and prompt_tokens > 4096:
                    print(f"[Warning] Cache hit rate low ({cache_hit_rate:.1%}). "
                          f"Inspect dynamic context placement or prefix drift.")

                print(f"\n[Token & Cache Telemetry]")
                print(f" Prompt Tokens: {prompt_tokens} (Cached: {cached_tokens} | Uncached: {uncached_prompt_tokens})")
                print(f" Context Cache Hit Rate: {cache_hit_rate:.2%}")
                print(f" Completion Tokens: {completion_tokens}")
                print(f" Total Tokens: {total_tokens}")
                print(f" Calculated Cost: ${cost:.6f}")

            return response


if __name__ == "__main__":
    try:
        run_travel_trip_pipeline()
    finally:
        flush_tracer()


"""
task example


# New Task-based Remote A2A Sub-Agent for user verification/confirmation
final_verification = RemoteA2aAgent(
    name="final_verification_agent",
    description="Performs asynchronous verification with the user to confirm itinerary selections and payments.",
    agent_card=f"https://verification-service.partner-cloud.com{AGENT_CARD_WELL_KNOWN_PATH}",
    use_legacy=False,
    push_notification_config={"url": WEBHOOK_CALLBACK_URL, "token": "verification-auth-jwt"}
)

# --- Task Syntax Invocation ---
            # Using send_streaming_message to initiate an asynchronous Task 
            # and process task updates/status events incrementally.
            print("\n--- Initiating Async Task via final_verification ---")
            task_events = final_verification.send_streaming_message(
                message={
                    "contextId": TRIP_CONTEXT_ID,
                    "referenceTaskIds": ["task-hotel-shinjuku-99"],
                    "parts": [{"text": "Verify payment method and finalize booking for Shinjuku Vegan Dining."}]
                },
                headers=verification_headers
            )

            current_task_id = None
            task_state = None

            for event in task_events:
                # Handle Task status updates emitted by the remote agent
                if hasattr(event, "task_status"):
                    current_task_id = event.task_id
                    task_state = event.task_status.state
                    print(f"[Task Lifecycle] Task ID: {current_task_id} | State: {task_state}")

                    # Interrupted State: Human-in-the-Loop required
                    if task_state == "input-required":
                        print(f"[Task Interrupted] {event.task_status.message}")
                        
                        # Simulate user interaction/confirmation response
                        user_confirmation_text = "Confirmed. Proceed with payment via Visa ending in 4242."

                        print(f"\n--- Resuming Interrupted Task {current_task_id} with User Input ---")
                        resume_response = final_verification.send_message(
                            message={
                                "contextId": TRIP_CONTEXT_ID,
                                "taskId": current_task_id,
                                "referenceTaskIds": ["task-hotel-shinjuku-99"],
                                "parts": [{"text": user_confirmation_text}]
                            },
                            headers=verification_headers
                        )
                        print(f"[Task Finalized Output]: {resume_response}")
                        return resume_response

                elif hasattr(event, "task_artifact"):
                    print(f"[Task Artifact]: {event.task_artifact}")

            return task_events





            Agent gateway call

    hotel_subagent = RemoteA2aAgent(
    name="hotel_booking_specialist",
    description="Handles finding and booking hotel accommodations via Agent Gateway.",
    # Route request through the central Agent Gateway endpoint
    agent_card="https://agent-gateway.internal.bank.example/v1/agents/hotel-booking-specialist",
    use_legacy=False,
    push_notification_config={"url": WEBHOOK_CALLBACK_URL, "token": "signed-jwt-or-opaque-auth-token"}
)

# Prepare headers for the Agent Gateway call
gateway_headers = {}

# 1. Inject trace context (OpenTelemetry)
inject(gateway_headers)

# 2. Token for Agent Gateway verification (Caller's Agent Identity / SPIFFE token)
gateway_headers["Proxy-Authorization"] = f"Bearer {caller_spiffe_gateway_token}"

# 3. Audience-bound token for the downstream target agent
gateway_headers["Authorization"] = f"Bearer {target_subagent_access_token}"

# Execute call through the gateway
response = restaurant_subagent.send_message(
    message={
        "contextId": TRIP_CONTEXT_ID,
        "referenceTaskIds": ["task-hotel-shinjuku-99"],
        "parts": [{"text": "Find vegan dinner options near the hotel."}]
    },
    headers=gateway_headers
)

# Key Architectural Differences
# Decoupled Policy Enforcement: The Agent Gateway acts as the Policy Enforcement Point (PEP). 
# It validates the Proxy-Authorization header before allowing traffic to pass downstream.

No Direct Network Access: The calling agent no longer requires direct egress access to the remote 
subagent's domain.

Audience Binding & Isolation: Per Zero Trust rules, the target token in Authorization must be 
audience-bound (aud) specifically to the remote agent receiving the request, 
preventing token passthrough misuse.

"""