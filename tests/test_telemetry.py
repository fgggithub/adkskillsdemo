"""
Unit tests for token cost computation, Context Cache hit rate tracking, and OpenTelemetry helpers.
"""
from travel_concierge.telemetry.cost_tracker import (
    calculate_token_cost,
    extract_usage_from_response,
    track_llm_telemetry,
)
from travel_concierge.telemetry.tracer import inject_trace_context, extract_trace_context, init_tracer
from travel_concierge.tools.mock_services import MockAgentResponse, MockUsageMetadata


def test_calculate_token_cost_with_caching():
    # 10,000 prompt tokens (8,000 cached, 2,000 uncached) + 1,000 completion tokens
    # Uncached prompt: 2,000 * ($0.30 / 1M) = $0.00060
    # Cached prompt:   8,000 * ($0.075 / 1M) = $0.00060
    # Completion:      1,000 * ($2.50 / 1M) = $0.00250
    # Total cost = $0.00370
    # Cache hit rate = 8,000 / 10,000 = 80.0%
    metrics = calculate_token_cost(
        prompt_tokens=10000,
        cached_tokens=8000,
        completion_tokens=1000,
        input_price_per_1m=0.30,
        cached_input_price_per_1m=0.075,
        output_price_per_1m=2.50,
    )

    assert metrics.prompt_tokens == 10000
    assert metrics.cached_tokens == 8000
    assert metrics.uncached_prompt_tokens == 2000
    assert metrics.completion_tokens == 1000
    assert metrics.total_tokens == 11000
    assert pytest_approx(metrics.cache_hit_rate, 0.80)
    assert pytest_approx(metrics.cost_usd, 0.00370)


def pytest_approx(val, expected, tolerance=1e-5):
    return abs(val - expected) < tolerance


def test_calculate_token_cost_zero_tokens():
    metrics = calculate_token_cost(prompt_tokens=0, cached_tokens=0, completion_tokens=0)
    assert metrics.cache_hit_rate == 0.0
    assert metrics.cost_usd == 0.0


def test_extract_usage_from_mock_response():
    response = MockAgentResponse(
        text="Sample output",
        usage_metadata=MockUsageMetadata(
            prompt_token_count=1000,
            cached_content_token_count=600,
            candidates_token_count=200,
            total_token_count=1200,
        ),
    )
    usage = extract_usage_from_response(response)
    assert usage["prompt_tokens"] == 1000
    assert usage["cached_tokens"] == 600
    assert usage["completion_tokens"] == 200
    assert usage["total_tokens"] == 1200


def test_extract_usage_from_dict_response():
    dict_resp = {
        "usage_metadata": {
            "prompt_token_count": 500,
            "cached_content_token_count": 250,
            "candidates_token_count": 50,
            "total_token_count": 550,
        }
    }
    usage = extract_usage_from_response(dict_resp)
    assert usage["prompt_tokens"] == 500
    assert usage["cached_tokens"] == 250


def test_trace_context_propagation():
    tracer = init_tracer("test_service")
    carrier = {}
    with tracer.start_as_current_span("test_span") as span:
        inject_trace_context(carrier)
        assert len(carrier) > 0
