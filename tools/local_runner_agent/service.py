"""Explicit long-running supervisor for the local DCP Runner Agent.

The service is opt-in, processes one job at a time, polls only while running,
backs off on Gateway transport failures, and stops claiming work after a signal.
It does not provision infrastructure.
"""
from __future__ import annotations

from threading import Event

from .client import RunnerGatewayError
from .execution import ExecutionError


class RunnerAgentService:
    def __init__(
        self,
        pipeline,
        *,
        poll_interval_seconds: int = 5,
        max_backoff_seconds: int = 60,
        wait=None,
    ):
        if isinstance(poll_interval_seconds, bool) or not isinstance(poll_interval_seconds, int) or not 1 <= poll_interval_seconds <= 60:
            raise ValueError("poll interval must be between 1 and 60 seconds")
        if isinstance(max_backoff_seconds, bool) or not isinstance(max_backoff_seconds, int) or not 1 <= max_backoff_seconds <= 300:
            raise ValueError("maximum backoff must be between 1 and 300 seconds")
        self.pipeline = pipeline
        self.poll_interval_seconds = poll_interval_seconds
        self.max_backoff_seconds = max_backoff_seconds
        self.wait = wait

    def _pause(self, stop_event: Event, seconds: int):
        if self.wait is None:
            stop_event.wait(seconds)
        else:
            self.wait(seconds)

    def run(self, stop_event: Event, *, max_cycles: int | None = None) -> dict:
        if not hasattr(stop_event, "is_set") or not hasattr(stop_event, "wait"):
            raise ValueError("stop_event must provide is_set and wait")
        if max_cycles is not None and (
            isinstance(max_cycles, bool) or not isinstance(max_cycles, int) or max_cycles < 1
        ):
            raise ValueError("max_cycles must be a positive integer")
        summary = {
            "cycles": 0,
            "jobs_processed": 0,
            "idle_polls": 0,
            "gateway_errors": 0,
            "outcomes": {"succeeded": 0, "failed": 0, "cancelled": 0, "unconfirmed": 0},
            "stopped": True,
            "reason": "stop_requested",
        }
        backoff = 1
        while not stop_event.is_set():
            try:
                result = self.pipeline.run_once()
                summary["cycles"] += 1
                backoff = 1
                if result is None:
                    summary["idle_polls"] += 1
                    delay = self.poll_interval_seconds
                else:
                    summary["jobs_processed"] += 1
                    outcome = result.get("outcome") if isinstance(result, dict) else None
                    if outcome in summary["outcomes"]:
                        summary["outcomes"][outcome] += 1
                    delay = 0
            except RunnerGatewayError as exc:
                summary["cycles"] += 1
                summary["gateway_errors"] += 1
                if exc.status_code in (400, 401, 403, 404, 409):
                    summary["stopped"] = False
                    summary["reason"] = "runner_not_eligible"
                    break
                delay = backoff
                backoff = min(backoff * 2, self.max_backoff_seconds)
            except ExecutionError:
                summary["stopped"] = False
                summary["reason"] = "runner_not_eligible"
                break

            if max_cycles is not None and summary["cycles"] >= max_cycles:
                summary["reason"] = "max_cycles_reached"
                break
            if delay:
                self._pause(stop_event, delay)

        return summary
