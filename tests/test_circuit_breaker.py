"""
Unit tests for the MCP Circuit Breaker resilience pattern.
"""
import time
import pytest
from travel_concierge.security.circuit_breaker import (
    MCPCircuitBreaker,
    CircuitBreakerState,
    CircuitBreakerOpenException,
)


def test_circuit_breaker_initial_closed_state(fast_circuit_breaker):
    assert fast_circuit_breaker.state == CircuitBreakerState.CLOSED
    assert fast_circuit_breaker.failure_count == 0


def test_circuit_breaker_successful_execution(fast_circuit_breaker):
    @fast_circuit_breaker
    def successful_tool():
        return {"status": "success", "results": ["item1", "item2"]}

    result = successful_tool()
    assert result["status"] == "success"
    assert fast_circuit_breaker.state == CircuitBreakerState.CLOSED
    assert fast_circuit_breaker.failure_count == 0


def test_circuit_breaker_failure_accumulation_and_trip(fast_circuit_breaker):
    @fast_circuit_breaker
    def failing_tool():
        raise RuntimeError("Service unavailable 503")

    # First failure
    res1 = failing_tool()
    assert res1["status"] == "degraded_fallback"
    assert fast_circuit_breaker.state == CircuitBreakerState.CLOSED
    assert fast_circuit_breaker.failure_count == 1

    # Second failure
    res2 = failing_tool()
    assert res2["status"] == "degraded_fallback"
    assert fast_circuit_breaker.state == CircuitBreakerState.CLOSED
    assert fast_circuit_breaker.failure_count == 2

    # Third failure -> reaches threshold (3) -> trips to OPEN
    res3 = failing_tool()
    assert res3["status"] == "degraded_fallback"
    assert fast_circuit_breaker.state == CircuitBreakerState.OPEN
    assert fast_circuit_breaker.failure_count == 3


def test_circuit_breaker_fast_fail_when_open(fast_circuit_breaker):
    call_counter = 0

    @fast_circuit_breaker
    def target_tool():
        nonlocal call_counter
        call_counter += 1
        raise RuntimeError("Persistent error")

    # Trip to OPEN
    for _ in range(3):
        target_tool()

    assert fast_circuit_breaker.state == CircuitBreakerState.OPEN
    initial_calls = call_counter

    # Next call should immediately return degraded fallback without executing function
    res = target_tool()
    assert res["status"] == "degraded_fallback"
    assert res["circuit_state"] == "OPEN"
    assert call_counter == initial_calls  # Target function was not called!


def test_circuit_breaker_half_open_recovery(fast_circuit_breaker):
    should_fail = True

    @fast_circuit_breaker
    def flaky_tool():
        if should_fail:
            raise RuntimeError("Temporary outage")
        return {"status": "success", "results": ["recovered"]}

    # 1. Trip breaker to OPEN
    for _ in range(3):
        flaky_tool()
    assert fast_circuit_breaker.state == CircuitBreakerState.OPEN

    # 2. Wait for recovery timeout (0.1s in fixture)
    time.sleep(0.15)

    # 3. Next execution should transition to HALF-OPEN then recover to CLOSED
    should_fail = False
    res = flaky_tool()
    assert res["status"] == "success"
    assert fast_circuit_breaker.state == CircuitBreakerState.CLOSED
    assert fast_circuit_breaker.failure_count == 0


def test_circuit_breaker_execution_timeout():
    cb = MCPCircuitBreaker(execution_timeout=0.05, failure_threshold=2)

    @cb
    def slow_tool():
        time.sleep(0.1)
        return {"status": "success", "results": ["slow"]}

    res = slow_tool()
    assert res["status"] == "degraded_fallback"
    assert "exceeded threshold" in res["error"]
    assert cb.failure_count == 1


def test_circuit_breaker_manual_reset(fast_circuit_breaker):
    @fast_circuit_breaker
    def failing():
        raise ValueError("Fail")

    for _ in range(3):
        failing()
    assert fast_circuit_breaker.state == CircuitBreakerState.OPEN

    fast_circuit_breaker.reset()
    assert fast_circuit_breaker.state == CircuitBreakerState.CLOSED
    assert fast_circuit_breaker.failure_count == 0
