"""
Configuration settings and environment management for the Travel Concierge Multi-Agent System.
"""
import os
from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class PricingConfig:
    """Token pricing configuration per 1 million tokens (USD)."""
    input_price_per_1m: float = float(os.getenv("INPUT_PRICE_PER_1M", "0.30"))
    cached_input_price_per_1m: float = float(os.getenv("CACHED_INPUT_PRICE_PER_1M", "0.075"))
    output_price_per_1m: float = float(os.getenv("OUTPUT_PRICE_PER_1M", "2.50"))


@dataclass
class CircuitBreakerConfig:
    """Circuit breaker configuration parameters."""
    failure_threshold: int = int(os.getenv("CB_FAILURE_THRESHOLD", "3"))
    recovery_timeout: float = float(os.getenv("CB_RECOVERY_TIMEOUT", "15.0"))
    execution_timeout: float = float(os.getenv("CB_EXECUTION_TIMEOUT", "3.0"))


@dataclass
class ServiceEndpoints:
    """External and internal service URLs."""
    zomato_mcp_url: str = os.getenv("ZOMATO_MCP_URL", "https://mcp-server.zomato.com/mcp")
    hotel_service_url: str = os.getenv(
        "HOTEL_SERVICE_URL", "https://hotel-booking-specialist-1085688005479.us-central1.run.app"
    )
    verification_service_url: str = os.getenv(
        "VERIFICATION_SERVICE_URL", "https://final-verification-agent-1085688005479.us-central1.run.app"
    )
    agent_gateway_url: str = os.getenv(
        "AGENT_GATEWAY_URL", "https://agent-gateway-pep-1085688005479.us-central1.run.app/v1"
    )
    restaurant_service_url: str = os.getenv(
        "RESTAURANT_SERVICE_URL", "https://restaurant-booking-specialist-1085688005479.us-central1.run.app"
    )
    webhook_callback_url: str = os.getenv(
        "WEBHOOK_CALLBACK_URL", "https://travel-concierge.example.com/a2a/webhooks/push"
    )


@dataclass
class GenerationGuardrailsConfig:
    """LLM generation constraints and guardrails."""
    max_output_tokens: int = int(os.getenv("MAX_OUTPUT_TOKENS", "4096"))
    stop_sequences: List[str] = field(
        default_factory=lambda: ["END_OF_CONCIERGE_RESPONSE", "### END"]
    )
    response_mime_type: Optional[str] = os.getenv("RESPONSE_MIME_TYPE")
    thinking_budget: int = int(os.getenv("THINKING_BUDGET", "1024"))
    thinking_level: str = os.getenv("THINKING_LEVEL", "LOW")  # "LOW" or "HIGH"


@dataclass
class Settings:
    """Global application settings."""
    project_id: str = os.getenv("GOOGLE_CLOUD_PROJECT") or os.getenv("PROJECT_ID", "my-gcp-project")
    location: str = os.getenv("GOOGLE_CLOUD_LOCATION") or os.getenv("LOCATION", "us-central1")
    model_name: str = os.getenv("MODEL_NAME", "gemini-2.5-flash")
    base_model_name: str = os.getenv("BASE_MODEL_NAME", "gemini-3.5-flash")
    escalated_model_name: str = os.getenv("ESCALATED_MODEL_NAME", "gemini-3.5")
    environment: str = os.getenv("ENVIRONMENT", "development")
    log_level: str = os.getenv("LOG_LEVEL", "INFO")

    pricing: PricingConfig = field(default_factory=PricingConfig)
    circuit_breaker: CircuitBreakerConfig = field(default_factory=CircuitBreakerConfig)
    endpoints: ServiceEndpoints = field(default_factory=ServiceEndpoints)
    guardrails: GenerationGuardrailsConfig = field(default_factory=GenerationGuardrailsConfig)

    @property
    def PROJECT_ID(self) -> str:
        return self.project_id

    @property
    def REGION(self) -> str:
        return self.location

    @property
    def DEFAULT_MODEL(self) -> str:
        return self.model_name


# Global settings singleton
settings = Settings()
