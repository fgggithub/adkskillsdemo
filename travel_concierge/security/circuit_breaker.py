"""
Circuit Breaker pattern for protecting MCP tool invocations and downstream remote services.
"""
import enum
import logging
import threading
import time
from typing import Callable, Any, Dict, Optional

logger = logging.getLogger("travel_concierge.circuit_breaker")


class CircuitBreakerState(str, enum.Enum):
    CLOSED = "CLOSED"
    OPEN = "OPEN"
    HALF_OPEN = "HALF-OPEN"


class CircuitBreakerOpenException(Exception):
    """Raised when the circuit breaker is OPEN and calls are rejected."""
    pass


class MCPCircuitBreaker:
    """
    Production-grade Circuit Breaker with configurable failure thresholds,
    recovery timeouts, and execution deadlines.
    """

    def __init__(
        self,
        name: str = "mcp_circuit_breaker",
        failure_threshold: int = 3,
        recovery_timeout: float = 15.0,
        execution_timeout: float = 3.0,
        raise_on_open: bool = False,
    ):
        self.name = name
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.execution_timeout = execution_timeout
        self.raise_on_open = raise_on_open

        self.failure_count = 0
        self.success_count = 0
        self.state = CircuitBreakerState.CLOSED
        self.last_state_change = time.time()
        self._lock = threading.Lock()

    def get_status(self) -> Dict[str, Any]:
        """Returns current health and metric status of the circuit breaker."""
        with self._lock:
            return {
                "name": self.name,
                "state": self.state.value,
                "failure_count": self.failure_count,
                "failure_threshold": self.failure_threshold,
                "recovery_timeout": self.recovery_timeout,
                "execution_timeout": self.execution_timeout,
                "last_state_change": self.last_state_change,
            }

    def reset(self):
        """Manually resets the circuit breaker to CLOSED state."""
        with self._lock:
            self.state = CircuitBreakerState.CLOSED
            self.failure_count = 0
            self.last_state_change = time.time()
            logger.info(f"[{self.name}] Circuit Breaker manually reset to CLOSED.")

    def __call__(self, func: Callable) -> Callable:
        def wrapper(*args, **kwargs):
            with self._lock:
                now = time.time()
                if self.state == CircuitBreakerState.OPEN:
                    if now - self.last_state_change > self.recovery_timeout:
                        self.state = CircuitBreakerState.HALF_OPEN
                        self.last_state_change = now
                        logger.info(f"[{self.name}] State transitioned to HALF-OPEN (testing service recovery).")
                    else:
                        logger.warning(f"[{self.name}] Circuit Breaker is OPEN. Fast failing call.")
                        if self.raise_on_open:
                            raise CircuitBreakerOpenException(
                                f"Circuit Breaker '{self.name}' is OPEN. Tool call blocked to protect service."
                            )
                        return {
                            "status": "degraded_fallback",
                            "error": f"Circuit breaker '{self.name}' is OPEN.",
                            "circuit_state": self.state.value,
                            "results": ["Cached/Default dining options near hotel"]
                        }

            try:
                start_time = time.time()
                result = func(*args, **kwargs)
                duration = time.time() - start_time

                if duration > self.execution_timeout:
                    raise TimeoutError(
                        f"MCP tool execution exceeded threshold ({duration:.2f}s > {self.execution_timeout}s)"
                    )

                if result is None or (isinstance(result, dict) and not result.get("results") and result.get("status") != "success"):
                    raise ValueError("MCP tool returned null or empty result payload.")

                with self._lock:
                    if self.state in (CircuitBreakerState.HALF_OPEN, CircuitBreakerState.OPEN):
                        logger.info(f"[{self.name}] Successful execution in {self.state.value}. Resetting to CLOSED.")
                    self.state = CircuitBreakerState.CLOSED
                    self.failure_count = 0
                    self.success_count += 1

                return result

            except Exception as e:
                with self._lock:
                    self.failure_count += 1
                    logger.error(
                        f"[{self.name}] Execution failure #{self.failure_count}: {e}"
                    )
                    if self.failure_count >= self.failure_threshold or self.state == CircuitBreakerState.HALF_OPEN:
                        self.state = CircuitBreakerState.OPEN
                        self.last_state_change = time.time()
                        logger.warning(
                            f"[{self.name}] Failure threshold reached. State transitioned to OPEN."
                        )

                if self.raise_on_open and isinstance(e, CircuitBreakerOpenException):
                    raise

                return {
                    "status": "degraded_fallback",
                    "error": str(e),
                    "circuit_state": self.state.value,
                    "results": ["Cached/Default dining options near hotel"]
                }

        return wrapper
