"""Mock provider for exercising the benchmark pipeline."""

from __future__ import annotations

from dataclasses import dataclass

from agent_skill_bench.fixtures import ResolvedBenchmarkCase

from .base import ProviderRunResponse


@dataclass(slots=True)
class MockBenchmarkProvider:
    """A deterministic provider for local testing and plumbing checks."""

    name: str = "mock"

    def run_case(self, case: ResolvedBenchmarkCase) -> ProviderRunResponse:
        return ProviderRunResponse(
            output_text=f"[mock:{case.mode.value}] {case.render_prompt()}",
            metadata={
                "case_id": case.id,
                "suite_id": case.suite_id,
                "kind": case.kind.value,
                "execution_profile": case.execution_profile.name,
                "skill_count": len(case.skill_paths),
            },
        )
