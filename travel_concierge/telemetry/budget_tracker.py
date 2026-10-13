"""
Budget Tracking & Financial Guardrails Module.
Tracks project token consumption and cloud operational spend against a strict $5.00 USD budget.
Supports auditable reporting and teardown residual-cost verification.
"""
import os
import json
import logging
from dataclasses import dataclass, asdict
from typing import Dict, Any, Optional

logger = logging.getLogger("travel_concierge.telemetry.budget")

BUDGET_STATE_FILE = os.path.join(os.path.dirname(__file__), "budget_state.json")
DEFAULT_BUDGET_LIMIT_USD = 5.00


@dataclass
class BudgetState:
    budget_limit_usd: float = DEFAULT_BUDGET_LIMIT_USD
    cumulative_cost_usd: float = 0.0
    total_prompt_tokens: int = 0
    total_cached_tokens: int = 0
    total_completion_tokens: int = 0
    total_invocations: int = 0

    @property
    def remaining_budget_usd(self) -> float:
        return max(0.0, self.budget_limit_usd - self.cumulative_cost_usd)

    @property
    def budget_utilized_percent(self) -> float:
        return (self.cumulative_cost_usd / self.budget_limit_usd * 100.0) if self.budget_limit_usd > 0 else 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "budget_limit_usd": round(self.budget_limit_usd, 4),
            "cumulative_cost_usd": round(self.cumulative_cost_usd, 6),
            "remaining_budget_usd": round(self.remaining_budget_usd, 6),
            "budget_utilized_percent": round(self.budget_utilized_percent, 2),
            "total_prompt_tokens": self.total_prompt_tokens,
            "total_cached_tokens": self.total_cached_tokens,
            "total_completion_tokens": self.total_completion_tokens,
            "total_invocations": self.total_invocations,
        }


class ProjectBudgetTracker:
    """
    Tracks agent financial burn rate against the allocated project budget.
    Raises warnings at 80% utilization and halts/warns if budget is exhausted.
    """

    def __init__(self, limit_usd: float = DEFAULT_BUDGET_LIMIT_USD, state_file: str = BUDGET_STATE_FILE):
        self.state_file = state_file
        self.state = self._load_state(limit_usd)

    def _load_state(self, limit_usd: float) -> BudgetState:
        if os.path.exists(self.state_file):
            try:
                with open(self.state_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    return BudgetState(
                        budget_limit_usd=data.get("budget_limit_usd", limit_usd),
                        cumulative_cost_usd=data.get("cumulative_cost_usd", 0.0),
                        total_prompt_tokens=data.get("total_prompt_tokens", 0),
                        total_cached_tokens=data.get("total_cached_tokens", 0),
                        total_completion_tokens=data.get("total_completion_tokens", 0),
                        total_invocations=data.get("total_invocations", 0),
                    )
            except Exception as e:
                logger.warning(f"Could not load budget state from {self.state_file}: {e}")
        return BudgetState(budget_limit_usd=limit_usd)

    def _save_state(self):
        try:
            with open(self.state_file, "w", encoding="utf-8") as f:
                json.dump(asdict(self.state), f, indent=2)
        except Exception as e:
            logger.warning(f"Could not save budget state: {e}")

    def record_spend(
        self,
        cost_usd: float,
        prompt_tokens: int = 0,
        cached_tokens: int = 0,
        completion_tokens: int = 0,
    ) -> BudgetState:
        """Records expenditure and updates cumulative ledger."""
        self.state.cumulative_cost_usd += cost_usd
        self.state.total_prompt_tokens += prompt_tokens
        self.state.total_cached_tokens += cached_tokens
        self.state.total_completion_tokens += completion_tokens
        self.state.total_invocations += 1
        self._save_state()

        if self.state.budget_utilized_percent >= 100.0:
            logger.error(
                f"[BUDGET EXHAUSTED] Total spend ${self.state.cumulative_cost_usd:.4f} exceeded limit ${self.state.budget_limit_usd:.2f}!"
            )
        elif self.state.budget_utilized_percent >= 80.0:
            logger.warning(
                f"[BUDGET ALERT] 80% threshold reached: spend=${self.state.cumulative_cost_usd:.4f} / limit=${self.state.budget_limit_usd:.2f} ({self.state.budget_utilized_percent:.1f}%)"
            )
        else:
            logger.info(
                f"[Budget Tracked] Spent: ${cost_usd:.6f} | Total: ${self.state.cumulative_cost_usd:.4f} / ${self.state.budget_limit_usd:.2f} ({self.state.budget_utilized_percent:.1f}%)"
            )

        return self.state

    def get_report(self) -> Dict[str, Any]:
        """Returns structured budget report."""
        return self.state.to_dict()

    def get_budget_status(self) -> Dict[str, Any]:
        """Alias for get_report."""
        return self.get_report()

    def reset(self):
        """Resets the budget counter."""
        self.state = BudgetState(budget_limit_usd=DEFAULT_BUDGET_LIMIT_USD)
        self._save_state()


# Default singleton instance
project_budget = ProjectBudgetTracker()
budget_tracker = project_budget
