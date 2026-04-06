"""CLI tests."""

from __future__ import annotations

import json
from pathlib import Path

from agent_skill_bench.cli import main


def test_cli_discover_outputs_case_paths(tmp_path: Path, capsys):
    case_dir = tmp_path / "agent-skill-uiux" / "benchmarks" / "cases"
    case_dir.mkdir(parents=True)
    case = case_dir / "sample.json"
    case.write_text("{}", encoding="utf-8")

    exit_code = main(["discover", str(tmp_path)])

    assert exit_code == 0
    output = json.loads(capsys.readouterr().out)
    assert output == [str(case)]


def test_cli_run_mock_outputs_results(tmp_path: Path, capsys, monkeypatch):
    skill_dir = tmp_path / "agent-skill-uiux" / "skills" / "uiux"
    suite_dir = tmp_path / "agent-skill-uiux" / "benchmarks"
    case_dir = suite_dir / "cases"
    case_dir.mkdir(parents=True)
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text("Skill instructions", encoding="utf-8")
    (suite_dir / "suite.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "suite_id": "uiux",
                "title": "UIUX Suite",
                "default_skills": ["../skills/uiux"],
                "default_execution_policy": "isolated_prompt",
                "default_rule_policy": "uiux-default",
                "rule_policies": {
                    "uiux-default": {
                        "forbid_code_fences": True,
                        "require_first_heading": True,
                        "mode_rules": {
                            "Generate": [
                                {
                                    "code": "generate_has_layout_blocks",
                                    "kind": "section_non_empty",
                                    "section": "Layout Blocks",
                                    "message": "Layout Blocks section is non-empty."
                                }
                            ]
                        }
                    }
                },
                "prompt_contract": {
                    "mode_headings": {
                        "Generate": ["Screen Goal", "Layout Blocks"]
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    case = case_dir / "sample.json"
    case.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "id": "uiux.generate.cli",
                "title": "CLI Case",
                "mode": "Generate",
                "prompt": "Design a dashboard.",
                "expectations": {
                    "must_cover": [],
                    "must_avoid": [],
                    "golden_signals": []
                }
            }
        ),
        encoding="utf-8",
    )

    monkeypatch.chdir(tmp_path)

    exit_code = main(["run", "--candidate-runtime", "mock", "--case", str(case)])

    assert exit_code == 0
    captured = capsys.readouterr()
    output = json.loads(captured.out)
    assert len(output) == 1
    assert output[0]["case_id"] == "uiux.generate.cli"
    assert output[0]["candidate_runtime_name"] == "mock"
    assert output[0]["candidate_outcome"]["status"] == "succeeded"
    assert output[0]["skill_paths"] == [str(skill_dir.resolve())]
    assert output[0]["skill_binding"]["requested_skills"] == ["uiux"]
    assert output[0]["skill_binding"]["registration_status"] == "unconfirmed"
    assert output[0]["output_text"].startswith("[mock:Generate]")
    assert output[0]["rule_assessment"]["policy"] == "uiux-default"
    saved_prefix = "Saved benchmark results to "
    assert captured.err.startswith(saved_prefix)
    saved_path = Path(captured.err.removeprefix(saved_prefix).strip())
    assert saved_path.exists()
    assert ".agent-skill-bench/runs" in saved_path.as_posix()


def test_cli_run_respects_explicit_output_and_skill_override(tmp_path: Path, capsys, monkeypatch):
    suite_dir = tmp_path / "agent-skill-uiux" / "benchmarks"
    case_dir = suite_dir / "cases"
    suite_dir.mkdir(parents=True)
    case_dir.mkdir()
    override_skill = tmp_path / "manual-skill"
    override_skill.mkdir()
    (override_skill / "SKILL.md").write_text("Manual skill", encoding="utf-8")
    (suite_dir / "suite.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "suite_id": "uiux",
                "title": "UIUX Suite",
                "default_execution_policy": "isolated_prompt"
            }
        ),
        encoding="utf-8",
    )
    case = case_dir / "sample.json"
    case.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "id": "uiux.generate.output",
                "title": "CLI Case",
                "mode": "Generate",
                "prompt": "Design a dashboard.",
                "expectations": {
                    "must_cover": [],
                    "must_avoid": [],
                    "golden_signals": []
                }
            }
        ),
        encoding="utf-8",
    )
    output_path = tmp_path / "artifacts" / "custom.json"
    monkeypatch.chdir(tmp_path)

    exit_code = main(
        [
            "run",
            "--candidate-runtime",
            "mock",
            "--case",
            str(case),
            "--output",
            str(output_path),
            "--skill",
            str(override_skill),
        ]
    )

    assert exit_code == 0
    captured = capsys.readouterr()
    assert captured.err.strip() == f"Saved benchmark results to {output_path}"
    persisted = json.loads(output_path.read_text(encoding="utf-8"))
    assert persisted[0]["case_id"] == "uiux.generate.output"
    assert persisted[0]["skill_paths"] == [str(override_skill.resolve())]
    assert persisted[0]["skill_binding"]["requested_skills"] == ["manual-skill"]


def test_cli_report_summarizes_saved_run_artifacts(tmp_path: Path, capsys):
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
                    "rule_assessment": {"passed": False, "failure_modes": ["no_code_fences"]},
                    "judge_assessment": {"judge_runtime_name": "mock", "passed": False},
                },
            ]
        ),
        encoding="utf-8",
    )

    exit_code = main(["report", str(artifact)])

    assert exit_code == 0
    output = json.loads(capsys.readouterr().out)
    assert output["total_runs"] == 2
    assert output["passed_runs"] == 1
    assert output["judged_runs"] == 2
    assert output["candidate_runtime_statuses"] == [{"key": "succeeded", "count": 2}]
    assert output["top_failure_modes"] == [{"code": "no_code_fences", "count": 1}]


def test_cli_run_can_attach_mock_judge_runtime(tmp_path: Path, capsys, monkeypatch):
    suite_dir = tmp_path / "agent-skill-uiux" / "benchmarks"
    case_dir = suite_dir / "cases"
    suite_dir.mkdir(parents=True)
    case_dir.mkdir()
    (suite_dir / "suite.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "suite_id": "uiux",
                "title": "UIUX Suite",
                "default_execution_policy": "isolated_prompt"
            }
        ),
        encoding="utf-8",
    )
    case = case_dir / "sample.json"
    case.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "id": "uiux.generate.judged",
                "title": "CLI Case",
                "mode": "Generate",
                "prompt": "Design a dashboard.",
                "expectations": {
                    "must_cover": [],
                    "must_avoid": [],
                    "golden_signals": []
                }
            }
        ),
        encoding="utf-8",
    )

    monkeypatch.chdir(tmp_path)
    exit_code = main(
        [
            "run",
            "--candidate-runtime",
            "mock",
            "--judge-runtime",
            "mock",
            "--case",
            str(case),
        ]
    )

    assert exit_code == 0
    output = json.loads(capsys.readouterr().out)
    assert output[0]["judge_assessment"]["judge_runtime_name"] == "mock"
    assert output[0]["judge_outcome"]["status"] == "succeeded"
    assert output[0]["judge_assessment"]["dimensions"][0]["name"] == "contract_adherence"


def test_cli_reevaluate_recomputes_rule_assessment_from_saved_artifact(tmp_path: Path, capsys):
    suite_dir = tmp_path / "agent-skill-uiux" / "benchmarks"
    case_dir = suite_dir / "cases"
    suite_dir.mkdir(parents=True)
    case_dir.mkdir()
    (suite_dir / "suite.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "suite_id": "uiux",
                "title": "UIUX Suite",
                "default_execution_policy": "isolated_prompt",
                "default_rule_policy": "uiux-default",
                "rule_policies": {
                    "uiux-default": {
                        "forbid_code_fences": True,
                        "require_first_heading": True,
                        "mode_rules": {
                            "Generate": [
                                {
                                    "code": "generate_has_layout_blocks",
                                    "kind": "section_non_empty",
                                    "section": "Layout Blocks",
                                    "message": "Layout Blocks section is non-empty."
                                }
                            ]
                        }
                    }
                },
                "prompt_contract": {
                    "mode_headings": {
                        "Generate": ["Screen Goal", "Layout Blocks"]
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    case = case_dir / "sample.json"
    case.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "id": "uiux.generate.reevaluate-cli",
                "title": "CLI Reevaluate Case",
                "mode": "Generate",
                "prompt": "Design a dashboard.",
                "expectations": {
                    "must_cover": [],
                    "must_avoid": [],
                    "golden_signals": []
                }
            }
        ),
        encoding="utf-8",
    )
    artifact = tmp_path / "runs.json"
    artifact.write_text(
        json.dumps(
            [
                {
                    "case_id": "uiux.generate.reevaluate-cli",
                    "suite_id": "uiux",
                    "candidate_runtime_name": "mock",
                    "mode": "Generate",
                    "kind": "prompt",
                    "execution_policy": "isolated_prompt",
                    "rule_policy": "uiux-default",
                    "skill_paths": [],
                    "output_text": "## Screen Goal\n\nGoal\n\n## Layout Blocks\n\nBlocks",
                    "duration_seconds": 1.0,
                    "metadata": {},
                    "skill_binding": {
                        "requested_skills": [],
                        "injected_skills": [],
                        "registered_skills": [],
                        "registration_status": "not_requested",
                        "registration_confirmed": None,
                        "registration_evidence": None,
                        "usage_confirmed": None
                    },
                    "source_path": str(case),
                }
            ]
        ),
        encoding="utf-8",
    )
    output_path = tmp_path / "reevaluated.json"

    exit_code = main(["reevaluate", str(artifact), "--output", str(output_path)])

    assert exit_code == 0
    captured = capsys.readouterr()
    assert captured.err.strip() == f"Saved reevaluated benchmark results to {output_path}"
    reevaluated = json.loads(output_path.read_text(encoding="utf-8"))
    assert reevaluated[0]["candidate_outcome"]["status"] == "succeeded"
    assert reevaluated[0]["rule_assessment"]["passed"] is True
