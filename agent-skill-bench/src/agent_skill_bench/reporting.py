"""Aggregation helpers for saved benchmark run artifacts."""

from __future__ import annotations

from collections import Counter, defaultdict
import json
from pathlib import Path


def load_run_artifacts(paths: list[str | Path]) -> list[dict[str, object]]:
    """Load one or more saved run-artifact JSON files."""

    records: list[dict[str, object]] = []
    for path_value in paths:
        path = Path(path_value)
        payload = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload, list):
            raise ValueError(f"Run artifact {path} must contain a JSON list.")
        for index, item in enumerate(payload):
            if not isinstance(item, dict):
                raise ValueError(f"Run artifact {path} item {index} must be a JSON object.")
            records.append(dict(item))
    return records


def summarize_run_artifacts(records: list[dict[str, object]]) -> dict[str, object]:
    """Build a generic summary over saved benchmark run artifacts."""

    total_runs = len(records)
    passed_runs = 0
    judged_runs = 0
    judge_passed_runs = 0
    by_suite: dict[str, dict[str, int]] = defaultdict(_empty_bucket)
    by_mode: dict[str, dict[str, int]] = defaultdict(_empty_bucket)
    by_provider: dict[str, dict[str, int]] = defaultdict(_empty_bucket)
    by_judge: dict[str, dict[str, int]] = defaultdict(_empty_bucket)
    failure_modes = Counter()

    for record in records:
        evaluation = record.get("evaluation")
        evaluation_passed = bool(isinstance(evaluation, dict) and evaluation.get("passed") is True)
        if evaluation_passed:
            passed_runs += 1

        suite_id = str(record.get("suite_id", "<unknown>"))
        mode = str(record.get("mode", "<unknown>"))
        provider_name = str(record.get("provider_name", "<unknown>"))

        _update_bucket(by_suite[suite_id], evaluation_passed)
        _update_bucket(by_mode[mode], evaluation_passed)
        _update_bucket(by_provider[provider_name], evaluation_passed)

        judge_evaluation = record.get("judge_evaluation")
        if isinstance(judge_evaluation, dict):
            judged_runs += 1
            judge_passed = judge_evaluation.get("passed") is True
            if judge_passed:
                judge_passed_runs += 1
            judge_name = str(judge_evaluation.get("judge_name", "<unknown>"))
            _update_bucket(by_judge[judge_name], judge_passed)

        if isinstance(evaluation, dict):
            for code in evaluation.get("failure_modes", []):
                if isinstance(code, str):
                    failure_modes[code] += 1

    return {
        "total_runs": total_runs,
        "passed_runs": passed_runs,
        "failed_runs": total_runs - passed_runs,
        "pass_rate": _pass_rate(passed_runs, total_runs),
        "judged_runs": judged_runs,
        "judge_passed_runs": judge_passed_runs,
        "judge_pass_rate": _pass_rate(judge_passed_runs, judged_runs),
        "by_suite": _sorted_group_summary(by_suite),
        "by_mode": _sorted_group_summary(by_mode),
        "by_provider": _sorted_group_summary(by_provider),
        "by_judge": _sorted_group_summary(by_judge),
        "top_failure_modes": [
            {"code": code, "count": count}
            for code, count in failure_modes.most_common()
        ],
    }


def _empty_bucket() -> dict[str, int]:
    """Return an empty counter bucket."""

    return {"total": 0, "passed": 0, "failed": 0}


def _update_bucket(bucket: dict[str, int], passed: bool) -> None:
    """Update one grouped summary bucket."""

    bucket["total"] += 1
    if passed:
        bucket["passed"] += 1
    else:
        bucket["failed"] += 1


def _sorted_group_summary(groups: dict[str, dict[str, int]]) -> list[dict[str, object]]:
    """Convert grouped counters into a sorted list."""

    summary: list[dict[str, object]] = []
    for key in sorted(groups):
        bucket = groups[key]
        summary.append(
            {
                "key": key,
                "total": bucket["total"],
                "passed": bucket["passed"],
                "failed": bucket["failed"],
                "pass_rate": _pass_rate(bucket["passed"], bucket["total"]),
            }
        )
    return summary


def _pass_rate(passed: int, total: int) -> float | None:
    """Return a normalized pass rate."""

    if total == 0:
        return None
    return passed / total
