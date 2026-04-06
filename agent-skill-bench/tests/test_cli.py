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
                "default_execution_profile": "isolated_prompt",
                "default_evaluation_profile": "uiux-default",
                "evaluation_profiles": {
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
                "benchmark_prompt": {
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
                    "golden_signals": [],
                },
            }
        ),
        encoding="utf-8",
    )

    monkeypatch.chdir(tmp_path)

    exit_code = main(["run", "--provider", "mock", "--case", str(case)])

    assert exit_code == 0
    captured = capsys.readouterr()
    output = json.loads(captured.out)
    assert len(output) == 1
    assert output[0]["case_id"] == "uiux.generate.cli"
    assert output[0]["provider_name"] == "mock"
    assert output[0]["skill_paths"] == [str(skill_dir.resolve())]
    assert output[0]["skill_binding"]["requested_skills"] == ["uiux"]
    assert output[0]["skill_binding"]["registration_status"] == "unconfirmed"
    assert output[0]["output_text"].startswith("[mock:Generate]")
    assert output[0]["evaluation"]["profile"] == "uiux-default"
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
                    "default_execution_profile": "isolated_prompt",
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
                    "golden_signals": [],
                },
            }
        ),
        encoding="utf-8",
    )
    output_path = tmp_path / "artifacts" / "custom.json"
    monkeypatch.chdir(tmp_path)

    exit_code = main(
        [
            "run",
            "--provider",
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
