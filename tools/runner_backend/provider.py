"""Provider boundary for ephemeral macOS cloud runners."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class RunnerInstance:
    provider_id: str
    state: str
    runner_name: str | None = None
    labels: tuple[str, ...] = ()
    detail: str | None = None


class RunnerProvider(Protocol):
    def provision(self, payload: dict) -> RunnerInstance: ...
    def status(self, provider_id: str) -> RunnerInstance: ...
    def terminate(self, provider_id: str) -> RunnerInstance: ...
