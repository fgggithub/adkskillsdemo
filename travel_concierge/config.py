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


def _resolve_project_number() -> str:
    """Detects active GCP project number dynamically for Cloud Run service URLs."""
    # 1. Direct environment variable
    if os.getenv("PROJECT_NUMBER"):
        return os.environ["PROJECT_NUMBER"].strip()

    # 2. Compute metadata server (when running on Cloud Run, GCE, GKE)
    try:
        import urllib.request
        req = urllib.request.Request(
            "http://metadata.google.internal/computeMetadata/v1/project/numeric-project-id",
            headers={"Metadata-Flavor": "Google"}
        )
        with urllib.request.urlopen(req, timeout=0.5) as resp:
            val = resp.read().decode("utf-8").strip()
            if val.isdigit() and val != "0":
                return val
    except Exception:
        pass

    # Determine active project ID
    active_project_id = os.getenv("PROJECT_ID") or os.getenv("GOOGLE_CLOUD_PROJECT", "")
    if not active_project_id:
        try:
            import subprocess
            res_p = subprocess.run(
                ["gcloud", "config", "get-value", "project"],
                capture_output=True,
                text=True,
                timeout=2.0,
                check=False
            )
            if res_p.returncode == 0 and res_p.stdout.strip():
                active_project_id = res_p.stdout.strip()
        except Exception:
            pass

    # 3. Check deployment config if it matches active project
    try:
        import json
        from pathlib import Path
        repo_root = Path(__file__).resolve().parent.parent
        cfg_paths = [
            repo_root / "deploy" / "gemini_enterprise_app_config.json",
            Path("/app/deploy/gemini_enterprise_app_config.json"),
            Path("deploy/gemini_enterprise_app_config.json"),
        ]
        for cfg_file in cfg_paths:
            if cfg_file.is_file():
                with open(cfg_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    cfg_pid = data.get("project_id", "")
                    pnum = str(data.get("project_number", "")).strip()
                    if pnum.isdigit() and (not active_project_id or cfg_pid == active_project_id):
                        return pnum
    except Exception:
        pass

    # 4. Query via gcloud CLI using active project
    if active_project_id:
        try:
            import subprocess
            res = subprocess.run(
                ["gcloud", "projects", "describe", active_project_id, "--format=value(projectNumber)"],
                capture_output=True,
                text=True,
                timeout=5.0,
                check=False
            )
            if res.returncode == 0 and res.stdout.strip().isdigit():
                return res.stdout.strip()
        except Exception:
            pass

    # 5. Inspect terraform state if present
    try:
        import re
        from pathlib import Path
        repo_root = Path(__file__).resolve().parent.parent
        tfstate_paths = [
            repo_root / "deploy" / "terraform" / "terraform.tfstate",
            Path("deploy/terraform/terraform.tfstate"),
        ]
        for tfstate in tfstate_paths:
            if tfstate.is_file():
                content = tfstate.read_text(encoding="utf-8")
                matches = re.findall(r"(?:projects/|run\.app.*?[-])(\d{10,14})", content)
                if matches:
                    return matches[0]
    except Exception:
        pass

    return "172253065956"


_DEFAULT_PROJECT_NUM = _resolve_project_number()


@dataclass
class ServiceEndpoints:
    """External and internal service URLs."""
    zomato_mcp_url: str = field(
        default_factory=lambda: os.getenv("ZOMATO_MCP_URL", "https://mcp-server.zomato.com/mcp")
    )
    hotel_service_url: str = field(
        default_factory=lambda: os.getenv(
            "HOTEL_SERVICE_URL", f"https://hotel-booking-specialist-{_resolve_project_number()}.us-central1.run.app"
        )
    )
    verification_service_url: str = field(
        default_factory=lambda: os.getenv(
            "VERIFICATION_SERVICE_URL", f"https://final-verification-agent-{_resolve_project_number()}.us-central1.run.app"
        )
    )
    agent_gateway_url: str = field(
        default_factory=lambda: os.getenv(
            "AGENT_GATEWAY_URL", f"https://agent-gateway-pep-{_resolve_project_number()}.us-central1.run.app"
        )
    )
    restaurant_service_url: str = field(
        default_factory=lambda: os.getenv(
            "RESTAURANT_SERVICE_URL", f"https://restaurant-booking-specialist-{_resolve_project_number()}.us-central1.run.app"
        )
    )
    webhook_callback_url: str = field(
        default_factory=lambda: os.getenv(
            "WEBHOOK_CALLBACK_URL", "https://travel-concierge.example.com/a2a/webhooks/push"
        )
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
