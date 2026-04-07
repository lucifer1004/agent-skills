"""Run-artifact reporting tests."""

from __future__ import annotations

import json
from pathlib import Path

from agent_skill_bench import compare_run_artifacts, load_run_artifacts, summarize_run_artifacts


def test_summarize_run_artifacts_groups_pass_fail_counts(tmp_path: Path):
    artifact = tmp_path / "runs.json"
    artifact.write_text(
        json.dumps(
            [
                {
                    "case_id": "uiux.generate.one",
                    "suite_id": "uiux",
                    "candidate_runtime_name": "mock",
                    "mode": "Generate",
                    "candidate_outcome": {"status": "succeeded", "code": None, "summary": None},
                    "rule_assessment": {"passed": True, "failure_modes": []},
                    "judge_assessment": {"judge_runtime_name": "mock", "passed": True},
                    "judge_outcome": {"status": "succeeded", "code": None, "summary": None},
                },
                {
                    "case_id": "uiux.review.one",
                    "suite_id": "uiux",
                    "candidate_runtime_name": "claude",
                    "mode": "Review",
                    "candidate_outcome": {
                        "status": "failed",
                        "code": "runtime_transport_failure",
                        "summary": "transport failed",
                    },
                    "rule_assessment": {
                        "passed": False,
                        "failure_modes": ["required_headings_present", "no_code_fences"],
                    },
                    "judge_assessment": {"judge_runtime_name": "mock", "passed": False},
                    "judge_outcome": {
                        "status": "failed",
                        "code": "structured_output_mismatch",
                        "summary": "schema mismatch",
                    },
                },
                {
                    "case_id": "pixi.generate.one",
                    "suite_id": "pixi",
                    "candidate_runtime_name": "mock",
                    "mode": "Generate",
                    "candidate_outcome": {"status": "succeeded", "code": None, "summary": None},
                    "rule_assessment": {"passed": False, "failure_modes": ["no_code_fences"]},
                },
            ]
        ),
        encoding="utf-8",
    )

    records = load_run_artifacts([artifact])
    summary = summarize_run_artifacts(records)

    assert summary["total_runs"] == 3
    assert summary["passed_runs"] == 1
    assert summary["failed_runs"] == 2
    assert summary["pass_rate"] == 1 / 3
    assert summary["judged_runs"] == 2
    assert summary["judge_passed_runs"] == 1
    assert summary["judge_pass_rate"] == 0.5
    assert summary["by_suite"][0]["key"] == "pixi"
    assert summary["by_suite"][0]["failed"] == 1
    assert summary["by_suite"][1]["key"] == "uiux"
    assert summary["by_suite"][1]["passed"] == 1
    assert summary["by_judge_runtime"] == [
        {"key": "mock", "total": 2, "passed": 1, "failed": 1, "pass_rate": 0.5}
    ]
    assert summary["candidate_runtime_statuses"] == [
        {"key": "failed", "count": 1},
        {"key": "succeeded", "count": 2},
    ]
    assert summary["candidate_runtime_failures"] == [
        {"key": "runtime_transport_failure", "count": 1}
    ]
    assert summary["judge_runtime_statuses"] == [
        {"key": "failed", "count": 1},
        {"key": "succeeded", "count": 1},
    ]
    assert summary["judge_runtime_failures"] == [
        {"key": "structured_output_mismatch", "count": 1}
    ]
    assert summary["top_failure_modes"][0] == {"code": "no_code_fences", "count": 2}


def test_compare_run_artifacts_reports_aggregate_and_matched_deltas():
    baseline = [
        {
            "case_id": "uiux.generate.one",
            "suite_id": "uiux",
            "candidate_runtime_name": "mock",
            "mode": "Generate",
            "candidate_outcome": {"status": "succeeded", "code": None, "summary": None},
            "rule_assessment": {"passed": True, "failure_modes": []},
        },
        {
            "case_id": "uiux.review.one",
            "suite_id": "uiux",
            "candidate_runtime_name": "mock",
            "mode": "Review",
            "candidate_outcome": {"status": "succeeded", "code": None, "summary": None},
            "rule_assessment": {"passed": False, "failure_modes": ["no_code_fences"]},
        },
    ]
    candidate = [
        {
            "case_id": "uiux.generate.one",
            "suite_id": "uiux",
            "candidate_runtime_name": "mock",
            "mode": "Generate",
            "candidate_outcome": {"status": "failed", "code": "runtime_timeout", "summary": "timeout"},
            "rule_assessment": {"passed": False, "failure_modes": ["starts_with_required_heading"]},
        },
        {
            "case_id": "pixi.generate.new",
            "suite_id": "pixi",
            "candidate_runtime_name": "mock",
            "mode": "Generate",
            "candidate_outcome": {"status": "succeeded", "code": None, "summary": None},
            "rule_assessment": {"passed": True, "failure_modes": []},
        },
    ]

    comparison = compare_run_artifacts(baseline, candidate)

    assert comparison["aggregate_deltas"]["pass_rate_delta"] == 0.0
    assert comparison["aggregate_deltas"]["candidate_runtime_failures"] == [
        {"key": "runtime_timeout", "baseline_count": 0, "candidate_count": 1, "delta": 1}
    ]
    assert comparison["aggregate_deltas"]["failure_modes"] == [
        {
            "key": "no_code_fences",
            "baseline_count": 1,
            "candidate_count": 0,
            "delta": -1,
        },
        {
            "key": "starts_with_required_heading",
            "baseline_count": 0,
            "candidate_count": 1,
            "delta": 1,
        },
    ]
    assert comparison["unmatched_runs"]["baseline_only"] == [
        {"suite_id": "uiux", "case_id": "uiux.review.one"}
    ]
    assert comparison["unmatched_runs"]["candidate_only"] == [
        {"suite_id": "pixi", "case_id": "pixi.generate.new"}
    ]
    assert comparison["matched_run_deltas"][0]["case_id"] == "uiux.generate.one"
    assert comparison["matched_run_deltas"][0]["candidate_outcome_changed"] is True
    assert comparison["matched_run_deltas"][0]["added_failure_modes"] == [
        "starts_with_required_heading"
    ]


def test_compare_run_artifacts_rejects_duplicate_benchmark_identity():
    duplicated = [
        {"case_id": "uiux.generate.one", "suite_id": "uiux"},
        {"case_id": "uiux.generate.one", "suite_id": "uiux"},
    ]

    try:
        compare_run_artifacts(duplicated, [])
    except ValueError as exc:
        assert "multiple runs" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("Expected duplicate identity to be rejected.")
