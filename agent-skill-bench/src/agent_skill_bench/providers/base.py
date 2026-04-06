"""Provider interface for running resolved benchmark cases."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

from agent_skill_bench.fixtures import ResolvedBenchmarkCase


@dataclass(slots=True)
class ProviderRunResponse:
    """Normalized provider output."""

    output_text: str
    raw_response: object | None = None
    metadata: dict[str, str | int | float | bool] = field(default_factory=dict)


class BenchmarkProvider(Protocol):
    """Minimal provider interface for benchmark runners."""

    name: str

    def run_case(self, case: ResolvedBenchmarkCase) -> ProviderRunResponse:
        """Execute one resolved benchmark case and return normalized output."""
