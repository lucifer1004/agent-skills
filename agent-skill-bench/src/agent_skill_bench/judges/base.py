"""Judge interfaces and result models for benchmark evaluation."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

from agent_skill_bench.fixtures import ResolvedBenchmarkCase


@dataclass(slots=True)
class JudgeDimensionScore:
    """One judge-scored dimension."""

    name: str
    score: int
    rationale: str

    def to_dict(self) -> dict[str, object]:
        """Convert one dimension score into JSON-serializable data."""

        return {
            "name": self.name,
            "score": self.score,
            "rationale": self.rationale,
        }


@dataclass(slots=True)
class JudgeEvaluation:
    """Normalized judge result for one benchmark run."""

    judge_name: str
    passed: bool
    summary: str
    dimensions: list[JudgeDimensionScore] = field(default_factory=list)
    metadata: dict[str, str | int | float | bool] = field(default_factory=dict)

    def to_dict(self) -> dict[str, object]:
        """Convert a judge result into JSON-serializable data."""

        return {
            "judge_name": self.judge_name,
            "passed": self.passed,
            "summary": self.summary,
            "dimensions": [dimension.to_dict() for dimension in self.dimensions],
            "metadata": dict(self.metadata),
        }


class BenchmarkJudge(Protocol):
    """Minimal interface for a benchmark judge."""

    name: str

    def evaluate_case(
        self,
        case: ResolvedBenchmarkCase,
        *,
        output_text: str,
        rule_evaluation: object | None = None,
    ) -> JudgeEvaluation:
        """Judge one benchmark output."""
