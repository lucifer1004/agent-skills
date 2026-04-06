"""Run-artifact reporting tests."""

from __future__ import annotations

import json
from pathlib import Path

from agent_skill_bench import load_run_artifacts, summarize_run_artifacts


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
                    "rule_assessment": {"passed": True, "failure_modes": []},
                    "judge_assessment": {"judge_runtime_name": "mock", "passed": True},
                },
                {
                    "case_id": "uiux.review.one",
                    "suite_id": "uiux",
                    "candidate_runtime_name": "claude",
                    "mode": "Review",
                    "rule_assessment": {
                        "passed": False,
                        "failure_modes": ["required_headings_present", "no_code_fences"],
                    },
                    "judge_assessment": {"judge_runtime_name": "mock", "passed": False},
                },
                {
                    "case_id": "pixi.generate.one",
                    "suite_id": "pixi",
                    "candidate_runtime_name": "mock",
                    "mode": "Generate",
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
    assert summary["top_failure_modes"][0] == {"code": "no_code_fences", "count": 2}
