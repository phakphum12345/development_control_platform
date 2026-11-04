"""Fail-closed live Azure budget gate for runner creation."""
from __future__ import annotations

import math
from datetime import datetime, timezone

from .policy import PolicyDenied


class AzureBudgetGuard:
    """Read the authoritative Azure budget before every new provision request."""

    def __init__(self, reader, projected_run_cost_usd: float):
        if isinstance(projected_run_cost_usd, bool) or not isinstance(projected_run_cost_usd, (int, float)):
            raise ValueError("Projected run cost must be numeric")
        if not math.isfinite(projected_run_cost_usd) or projected_run_cost_usd <= 0:
            raise ValueError("Projected run cost must be finite and positive")
        self.reader = reader
        self.projected_run_cost_usd = float(projected_run_cost_usd)

    def inspect(self):
        """Read current budget state for display; failures remain UNKNOWN to callers."""
        return self.reader.read()

    def authorize(self, active_count: int) -> None:
        if isinstance(active_count, bool) or not isinstance(active_count, int) or active_count < 0:
            raise PolicyDenied("Active runner count is invalid", 503)
        try:
            snapshot = self.reader.read()
        except Exception as exc:
            raise PolicyDenied("Live Azure budget is unavailable; provisioning denied", 503) from exc
        total_projected_cost = self.projected_run_cost_usd * (active_count + 1)
        if not math.isfinite(total_projected_cost) or not snapshot.permits(total_projected_cost):
            raise PolicyDenied("Azure budget or forecast ceiling would be exceeded", 429)

class ProviderBudgetGuard:
    """Generic guard for a provider's own independently sourced budget snapshot.

    The reader must be provider-specific and return a snapshot carrying the
    matching provider key plus a fail-closed permits(projected_cost) method.
    This deliberately cannot reuse an Azure snapshot for Orka.
    """

    def __init__(
        self, provider: str, reader, projected_run_cost_usd: float,
        max_age_seconds: int = 300,
    ):
        if not isinstance(provider, str) or not provider or len(provider) > 32:
            raise ValueError("Budget provider key is required")
        if (
            isinstance(projected_run_cost_usd, bool)
            or not isinstance(projected_run_cost_usd, (int, float))
            or not math.isfinite(projected_run_cost_usd)
            or projected_run_cost_usd <= 0
        ):
            raise ValueError("Projected run cost must be finite and positive")
        if reader is None or not callable(getattr(reader, "read", None)):
            raise ValueError("Provider budget reader is required")
        if (
            isinstance(max_age_seconds, bool)
            or not isinstance(max_age_seconds, int)
            or not 1 <= max_age_seconds <= 3600
        ):
            raise ValueError("Budget snapshot max age must be 1..3600 seconds")
        self.provider = provider
        self.reader = reader
        self.projected_run_cost_usd = float(projected_run_cost_usd)
        self.max_age_seconds = max_age_seconds

    def inspect(self):
        snapshot = self.reader.read()
        if getattr(snapshot, "provider", None) != self.provider:
            raise ValueError("Budget snapshot provider does not match guard")
        if not callable(getattr(snapshot, "permits", None)):
            raise ValueError("Provider budget snapshot is invalid")
        observed_at = getattr(snapshot, "observed_at", None)
        try:
            observed = datetime.fromisoformat(
                str(observed_at).replace("Z", "+00:00")
            )
        except (TypeError, ValueError) as exc:
            raise ValueError("Provider budget snapshot timestamp is invalid") from exc
        if observed.tzinfo is None:
            raise ValueError("Provider budget snapshot timestamp must include timezone")
        age = (datetime.now(timezone.utc) - observed).total_seconds()
        if age < -60 or age > self.max_age_seconds:
            raise ValueError("Provider budget snapshot is stale or from the future")
        return snapshot

    def authorize(self, active_count: int) -> None:
        if (
            isinstance(active_count, bool)
            or not isinstance(active_count, int)
            or active_count < 0
        ):
            raise PolicyDenied("Active runner count is invalid", 503)
        try:
            snapshot = self.inspect()
        except Exception as exc:
            raise PolicyDenied(
                "Live provider budget is unavailable; provisioning denied", 503
            ) from exc
        total_projected_cost = self.projected_run_cost_usd * (active_count + 1)
        if (
            not math.isfinite(total_projected_cost)
            or not snapshot.permits(total_projected_cost)
        ):
            raise PolicyDenied(
                "Provider budget or forecast ceiling would be exceeded", 429
            )
