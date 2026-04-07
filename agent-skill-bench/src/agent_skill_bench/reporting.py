"""Aggregation helpers for saved benchmark run artifacts."""

from __future__ import annotations

from collections import Counter, defaultdict
import json
from pathlib import Path
from typing import Mapping

from .domain import infer_candidate_outcome, infer_judge_outcome


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
    by_candidate_runtime: dict[str, dict[str, int]] = defaultdict(_empty_bucket)
    by_judge_runtime: dict[str, dict[str, int]] = defaultdict(_empty_bucket)
    candidate_runtime_statuses = Counter()
    candidate_runtime_failures = Counter()
    judge_runtime_statuses = Counter()
    judge_runtime_failures = Counter()
    failure_modes = Counter()

    for record in records:
        candidate_outcome = infer_candidate_outcome(record)
        rule_assessment = record.get("rule_assessment")
        rule_assessment_passed = bool(
            isinstance(rule_assessment, dict) and rule_assessment.get("passed") is True
        )
        if rule_assessment_passed:
            passed_runs += 1

        suite_id = str(record.get("suite_id", "<unknown>"))
        mode = str(record.get("mode", "<unknown>"))
        candidate_runtime_name = str(record.get("candidate_runtime_name", "<unknown>"))
        candidate_runtime_statuses[candidate_outcome.status] += 1
        if candidate_outcome.code is not None:
            candidate_runtime_failures[candidate_outcome.code] += 1

        _update_bucket(by_suite[suite_id], rule_assessment_passed)
        _update_bucket(by_mode[mode], rule_assessment_passed)
        _update_bucket(by_candidate_runtime[candidate_runtime_name], rule_assessment_passed)

        judge_assessment = record.get("judge_assessment")
        judge_outcome = infer_judge_outcome(record)
        if judge_outcome is not None:
            judge_runtime_statuses[judge_outcome.status] += 1
            if judge_outcome.code is not None:
                judge_runtime_failures[judge_outcome.code] += 1

        if isinstance(judge_assessment, dict):
            judged_runs += 1
            judge_passed = judge_assessment.get("passed") is True
            if judge_passed:
                judge_passed_runs += 1
            judge_name = str(judge_assessment.get("judge_runtime_name", "<unknown>"))
            _update_bucket(by_judge_runtime[judge_name], judge_passed)

        if isinstance(rule_assessment, dict):
            for code in rule_assessment.get("failure_modes", []):
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
        "by_candidate_runtime": _sorted_group_summary(by_candidate_runtime),
        "by_judge_runtime": _sorted_group_summary(by_judge_runtime),
        "candidate_runtime_statuses": _sorted_counter_summary(candidate_runtime_statuses),
        "candidate_runtime_failures": _sorted_counter_summary(candidate_runtime_failures),
        "judge_runtime_statuses": _sorted_counter_summary(judge_runtime_statuses),
        "judge_runtime_failures": _sorted_counter_summary(judge_runtime_failures),
        "top_failure_modes": [
            {"code": code, "count": count}
            for code, count in failure_modes.most_common()
        ],
    }


def compare_run_artifacts(
    baseline_records: list[dict[str, object]],
    candidate_records: list[dict[str, object]],
) -> dict[str, object]:
    """Compare two normalized run-artifact sets and surface regressions."""

    baseline_summary = summarize_run_artifacts(baseline_records)
    candidate_summary = summarize_run_artifacts(candidate_records)

    baseline_index = _index_by_benchmark_identity(baseline_records, label="baseline")
    candidate_index = _index_by_benchmark_identity(candidate_records, label="candidate")

    baseline_keys = set(baseline_index)
    candidate_keys = set(candidate_index)
    matched_keys = sorted(baseline_keys & candidate_keys)
    baseline_only_keys = sorted(baseline_keys - candidate_keys)
    candidate_only_keys = sorted(candidate_keys - baseline_keys)

    matched_run_deltas: list[dict[str, object]] = []
    for key in matched_keys:
        delta = _matched_run_delta(baseline_index[key], candidate_index[key])
        if delta is not None:
            matched_run_deltas.append(delta)

    return {
        "baseline_summary": baseline_summary,
        "candidate_summary": candidate_summary,
        "aggregate_deltas": {
            "pass_rate_delta": _numeric_delta(
                baseline_summary.get("pass_rate"),
                candidate_summary.get("pass_rate"),
            ),
            "judge_pass_rate_delta": _numeric_delta(
                baseline_summary.get("judge_pass_rate"),
                candidate_summary.get("judge_pass_rate"),
            ),
            "candidate_runtime_statuses": _delta_counter_summaries(
                baseline_summary.get("candidate_runtime_statuses"),
                candidate_summary.get("candidate_runtime_statuses"),
            ),
            "candidate_runtime_failures": _delta_counter_summaries(
                baseline_summary.get("candidate_runtime_failures"),
                candidate_summary.get("candidate_runtime_failures"),
            ),
            "judge_runtime_statuses": _delta_counter_summaries(
                baseline_summary.get("judge_runtime_statuses"),
                candidate_summary.get("judge_runtime_statuses"),
            ),
            "judge_runtime_failures": _delta_counter_summaries(
                baseline_summary.get("judge_runtime_failures"),
                candidate_summary.get("judge_runtime_failures"),
            ),
            "failure_modes": _delta_counter_summaries(
                baseline_summary.get("top_failure_modes"),
                candidate_summary.get("top_failure_modes"),
                key_field="code",
            ),
        },
        "group_deltas": {
            "by_suite": _delta_group_summaries(
                baseline_summary.get("by_suite"),
                candidate_summary.get("by_suite"),
            ),
            "by_mode": _delta_group_summaries(
                baseline_summary.get("by_mode"),
                candidate_summary.get("by_mode"),
            ),
        },
        "unmatched_runs": {
            "baseline_only": [_identity_payload(key) for key in baseline_only_keys],
            "candidate_only": [_identity_payload(key) for key in candidate_only_keys],
        },
        "matched_run_deltas": matched_run_deltas,
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


def _sorted_counter_summary(counter: Counter[str]) -> list[dict[str, object]]:
    """Convert a counter into a stable sorted list."""

    return [{"key": key, "count": counter[key]} for key in sorted(counter)]


def _index_by_benchmark_identity(
    records: list[dict[str, object]],
    *,
    label: str,
) -> dict[tuple[str, str], dict[str, object]]:
    """Index artifacts by suite/case identity and reject ambiguous duplicates."""

    indexed: dict[tuple[str, str], dict[str, object]] = {}
    for record in records:
        identity = _benchmark_identity(record)
        if identity in indexed:
            suite_id, case_id = identity
            raise ValueError(
                f"{label.capitalize()} artifact set contains multiple runs for {suite_id}/{case_id}."
            )
        indexed[identity] = record
    return indexed


def _benchmark_identity(record: Mapping[str, object]) -> tuple[str, str]:
    """Return the stable suite/case identity for one artifact record."""

    suite_id = record.get("suite_id")
    case_id = record.get("case_id")
    if not isinstance(suite_id, str) or not suite_id:
        raise ValueError("Artifact comparison requires a non-empty suite_id.")
    if not isinstance(case_id, str) or not case_id:
        raise ValueError("Artifact comparison requires a non-empty case_id.")
    return (suite_id, case_id)


def _identity_payload(identity: tuple[str, str]) -> dict[str, str]:
    """Convert one benchmark identity into JSON-serializable data."""

    suite_id, case_id = identity
    return {"suite_id": suite_id, "case_id": case_id}


def _matched_run_delta(
    baseline: dict[str, object],
    candidate: dict[str, object],
) -> dict[str, object] | None:
    """Return per-run deltas for one matched benchmark identity."""

    suite_id, case_id = _benchmark_identity(baseline)
    baseline_rule_passed = _rule_passed(baseline)
    candidate_rule_passed = _rule_passed(candidate)
    baseline_candidate_outcome = infer_candidate_outcome(baseline)
    candidate_candidate_outcome = infer_candidate_outcome(candidate)
    baseline_judge_outcome = infer_judge_outcome(baseline)
    candidate_judge_outcome = infer_judge_outcome(candidate)

    baseline_failure_modes = _failure_mode_set(baseline)
    candidate_failure_modes = _failure_mode_set(candidate)
    added_failure_modes = sorted(candidate_failure_modes - baseline_failure_modes)
    removed_failure_modes = sorted(baseline_failure_modes - candidate_failure_modes)

    candidate_outcome_changed = (
        baseline_candidate_outcome.to_dict() != candidate_candidate_outcome.to_dict()
    )
    judge_outcome_changed = _outcome_payload(
        baseline_judge_outcome
    ) != _outcome_payload(candidate_judge_outcome)
    rule_pass_changed = baseline_rule_passed != candidate_rule_passed

    if not any(
        [
            rule_pass_changed,
            candidate_outcome_changed,
            judge_outcome_changed,
            added_failure_modes,
            removed_failure_modes,
        ]
    ):
        return None

    return {
        "suite_id": suite_id,
        "case_id": case_id,
        "baseline_rule_passed": baseline_rule_passed,
        "candidate_rule_passed": candidate_rule_passed,
        "rule_pass_changed": rule_pass_changed,
        "baseline_candidate_outcome": baseline_candidate_outcome.to_dict(),
        "candidate_candidate_outcome": candidate_candidate_outcome.to_dict(),
        "candidate_outcome_changed": candidate_outcome_changed,
        "baseline_judge_outcome": _outcome_payload(baseline_judge_outcome),
        "candidate_judge_outcome": _outcome_payload(candidate_judge_outcome),
        "judge_outcome_changed": judge_outcome_changed,
        "added_failure_modes": added_failure_modes,
        "removed_failure_modes": removed_failure_modes,
    }


def _rule_passed(record: Mapping[str, object]) -> bool:
    """Return deterministic pass/fail from one artifact record."""

    rule_assessment = record.get("rule_assessment")
    return bool(isinstance(rule_assessment, Mapping) and rule_assessment.get("passed") is True)


def _failure_mode_set(record: Mapping[str, object]) -> set[str]:
    """Return deterministic failure-mode codes from one artifact record."""

    rule_assessment = record.get("rule_assessment")
    if not isinstance(rule_assessment, Mapping):
        return set()
    return {
        code
        for code in rule_assessment.get("failure_modes", [])
        if isinstance(code, str)
    }


def _outcome_payload(outcome: object) -> dict[str, object] | None:
    """Convert an optional outcome into plain data."""

    if outcome is None:
        return None
    return outcome.to_dict()


def _numeric_delta(baseline: object, candidate: object) -> float | None:
    """Return candidate-minus-baseline delta for optional floats."""

    if not isinstance(baseline, (int, float)) or not isinstance(candidate, (int, float)):
        return None
    return float(candidate) - float(baseline)


def _delta_counter_summaries(
    baseline: object,
    candidate: object,
    *,
    key_field: str = "key",
) -> list[dict[str, object]]:
    """Compute deltas between two summary-counter lists."""

    baseline_map = _summary_counter_map(baseline, key_field=key_field)
    candidate_map = _summary_counter_map(candidate, key_field=key_field)
    keys = sorted(set(baseline_map) | set(candidate_map))
    return [
        {
            "key": key,
            "baseline_count": baseline_map.get(key, 0),
            "candidate_count": candidate_map.get(key, 0),
            "delta": candidate_map.get(key, 0) - baseline_map.get(key, 0),
        }
        for key in keys
    ]


def _summary_counter_map(payload: object, *, key_field: str) -> dict[str, int]:
    """Convert summary list payloads into counter maps."""

    counter: dict[str, int] = {}
    if not isinstance(payload, list):
        return counter
    for item in payload:
        if not isinstance(item, Mapping):
            continue
        key = item.get(key_field)
        count = item.get("count")
        if key_field == "code":
            count = item.get("count")
        if key_field == "key" and not isinstance(count, int):
            count = item.get("count")
        if isinstance(key, str) and isinstance(count, int):
            counter[key] = count
    return counter


def _delta_group_summaries(
    baseline: object,
    candidate: object,
) -> list[dict[str, object]]:
    """Compute deltas between grouped pass-rate summaries."""

    baseline_map = _group_summary_map(baseline)
    candidate_map = _group_summary_map(candidate)
    keys = sorted(set(baseline_map) | set(candidate_map))
    deltas: list[dict[str, object]] = []
    for key in keys:
        baseline_bucket = baseline_map.get(key, {})
        candidate_bucket = candidate_map.get(key, {})
        deltas.append(
            {
                "key": key,
                "baseline_total": baseline_bucket.get("total", 0),
                "candidate_total": candidate_bucket.get("total", 0),
                "baseline_passed": baseline_bucket.get("passed", 0),
                "candidate_passed": candidate_bucket.get("passed", 0),
                "baseline_failed": baseline_bucket.get("failed", 0),
                "candidate_failed": candidate_bucket.get("failed", 0),
                "baseline_pass_rate": baseline_bucket.get("pass_rate"),
                "candidate_pass_rate": candidate_bucket.get("pass_rate"),
                "pass_rate_delta": _numeric_delta(
                    baseline_bucket.get("pass_rate"),
                    candidate_bucket.get("pass_rate"),
                ),
            }
        )
    return deltas


def _group_summary_map(payload: object) -> dict[str, dict[str, object]]:
    """Convert grouped summary lists into keyed mappings."""

    groups: dict[str, dict[str, object]] = {}
    if not isinstance(payload, list):
        return groups
    for item in payload:
        if not isinstance(item, Mapping):
            continue
        key = item.get("key")
        if isinstance(key, str):
            groups[key] = dict(item)
    return groups
