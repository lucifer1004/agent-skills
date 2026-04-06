"""Deterministic mock judge for tests and local plumbing validation."""

from __future__ import annotations

from agent_skill_bench.evaluation import BenchmarkEvaluation
from agent_skill_bench.fixtures import ResolvedBenchmarkCase

from .base import BenchmarkJudge, JudgeDimensionScore, JudgeEvaluation


class MockBenchmarkJudge(BenchmarkJudge):
    """Simple deterministic judge derived from existing rule-evaluation output."""

    name = "mock"

    def evaluate_case(
        self,
        case: ResolvedBenchmarkCase,
        *,
        output_text: str,
        rule_evaluation: BenchmarkEvaluation | None = None,
    ) -> JudgeEvaluation:
        """Return a stable, deterministic judge result."""

        contract_total = len(rule_evaluation.contract_checks) if rule_evaluation is not None else 0
        contract_passed = (
            sum(1 for check in rule_evaluation.contract_checks if check.passed)
            if rule_evaluation is not None
            else 0
        )
        rule_total = len(rule_evaluation.rule_checks) if rule_evaluation is not None else 0
        rule_passed = (
            sum(1 for check in rule_evaluation.rule_checks if check.passed)
            if rule_evaluation is not None
            else 0
        )

        contract_score = _scaled_score(contract_passed, contract_total)
        rule_score = _scaled_score(rule_passed, rule_total)
        passed = bool(rule_evaluation.passed) if rule_evaluation is not None else bool(output_text.strip())

        return JudgeEvaluation(
            judge_name=self.name,
            passed=passed,
            summary=(
                f"Mock judge scored {case.id} from existing rule evaluation."
                if rule_evaluation is not None
                else f"Mock judge scored {case.id} from non-empty output."
            ),
            dimensions=[
                JudgeDimensionScore(
                    name="contract_adherence",
                    score=contract_score,
                    rationale=f"{contract_passed}/{contract_total} contract checks passed.",
                ),
                JudgeDimensionScore(
                    name="rule_adherence",
                    score=rule_score,
                    rationale=f"{rule_passed}/{rule_total} rule checks passed.",
                ),
            ],
            metadata={
                "case_mode": case.mode.value,
                "used_rule_evaluation": rule_evaluation is not None,
                "output_chars": len(output_text),
            },
        )


def _scaled_score(passed: int, total: int) -> int:
    """Map check counts to a stable 0-3 score."""

    if total == 0:
        return 0
    ratio = passed / total
    if ratio >= 1.0:
        return 3
    if ratio >= 0.67:
        return 2
    if ratio > 0:
        return 1
    return 0
