"""Fail-closed live Azure budget gate for runner creation."""
from __future__ import annotations

from .policy import PolicyDenied


class AzureBudgetGuard:
    """Read the authoritative Azure budget before every new provision request."""

    def __init__(self, reader, projected_run_cost_usd: float):
        if isinstance(projected_run_cost_usd, bool) or not isinstance(projected_run_cost_usd, (int, float)):
            raise ValueError("Projected run cost must be numeric")
        if projected_run_cost_usd < 0:
            raise ValueError("Projected run cost must be non-negative")
        self.reader = reader
        self.projected_run_cost_usd = float(projected_run_cost_usd)

    def authorize(self, active_count: int) -> None:
        if isinstance(active_count, bool) or not isinstance(active_count, int) or active_count < 0:
            raise PolicyDenied("Active runner count is invalid", 503)
        try:
            snapshot = self.reader.read()
        except Exception as exc:
            raise PolicyDenied("Live Azure budget is unavailable; provisioning denied", 503) from exc
        if not snapshot.permits(self.projected_run_cost_usd):
            raise PolicyDenied("Azure budget or forecast ceiling would be exceeded", 429)
