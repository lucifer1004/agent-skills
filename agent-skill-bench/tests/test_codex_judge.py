"""Codex judge tests."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

from agent_skill_bench import (
    BenchmarkCase,
    BenchmarkEvaluation,
    BenchmarkMode,
    BenchmarkSuite,
    CodexCLIJudge,
    EvaluationCheck,
    ResolvedBenchmarkCase,
    get_execution_profile,
    get_judge,
)
import agent_skill_bench.judges.codex as codex_judge_module


def test_get_judge_returns_codex_judge():
    judge = get_judge("codex")

    assert isinstance(judge, CodexCLIJudge)


def test_codex_judge_runs_cli_with_output_schema(monkeypatch):
    case = ResolvedBenchmarkCase(
        suite=BenchmarkSuite(
            schema_version=1,
            suite_id="uiux",
            title="UIUX",
            default_execution_profile="isolated_prompt",
            default_judge_profile="uiux-judge",
                judge_profiles={
                    "uiux-judge": BenchmarkSuite.from_dict(
                        {
                            "schema_version": 1,
                            "suite_id": "uiux",
                        "title": "UIUX",
                        "default_execution_profile": "isolated_prompt",
                        "judge_profiles": {
                            "uiux-judge": {
                                "preamble": [
                                    "You are judging one benchmark output for a UI/UX skill."
                                ],
                                "shared_rules": [
                                    "Be strict about structural compliance before style commentary."
                                ],
                                "dimensions": [
                                    {
                                        "name": "task_fit",
                                        "description": "Does the answer perform the requested task?"
                                    },
                                    {
                                        "name": "contract_adherence",
                                        "description": "Does the answer follow the required output contract?"
                                    },
                                    {
                                        "name": "expectation_coverage",
                                        "description": "Does the answer cover the expectations?"
                                    },
                                    {
                                        "name": "actionability",
                                        "description": "Could a downstream user act on the answer?"
                                    }
                                ],
                                "pass_guidance": "Set passed=true only if the answer is benchmark-worthy.",
                                "include_rule_evaluation": True
                            }
                            }
                        }
                    ).judge_profiles["uiux-judge"],
                },
            ),
        case=BenchmarkCase(
            schema_version=1,
            id="uiux.generate.codex-judge",
            title="Judge Case",
            mode=BenchmarkMode.GENERATE,
            prompt="Design a dashboard.",
        ),
        execution_profile=get_execution_profile("isolated_prompt"),
    )
    evaluation = BenchmarkEvaluation(
        profile=None,
        passed=False,
        contract_checks=[EvaluationCheck(code="non_empty_output", passed=True, message="ok")],
        rule_checks=[],
        failure_modes=["required_headings_present"],
    )
    captured: dict[str, object] = {}

    def fake_run(cmd, *, capture_output, text, timeout, input):
        captured["cmd"] = cmd
        captured["timeout"] = timeout
        captured["input"] = input
        schema_path = Path(cmd[cmd.index("--output-schema") + 1])
        output_path = Path(cmd[cmd.index("--output-last-message") + 1])
        captured["schema"] = json.loads(schema_path.read_text(encoding="utf-8"))
        output_path.write_text(
            json.dumps(
                {
                    "passed": True,
                    "summary": "Strong benchmark answer.",
                    "dimensions": [
                        {"name": "task_fit", "score": 3, "rationale": "Matches the task."},
                        {"name": "contract_adherence", "score": 2, "rationale": "Mostly follows headings."},
                        {"name": "expectation_coverage", "score": 2, "rationale": "Covers key expectations."},
                        {"name": "actionability", "score": 3, "rationale": "Concrete enough to use."},
                    ],
                }
            ),
            encoding="utf-8",
        )
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(codex_judge_module.subprocess, "run", fake_run)

    result = CodexCLIJudge(timeout_seconds=12).evaluate_case(
        case,
        output_text="## Screen Goal\nA good answer.",
        rule_evaluation=evaluation,
    )

    assert captured["cmd"][:2] == ["codex", "exec"]
    assert "--output-schema" in captured["cmd"]
    assert captured["schema"]["type"] == "object"
    assert captured["schema"]["properties"]["dimensions"]["items"]["properties"]["name"]["enum"] == [
        "task_fit",
        "contract_adherence",
        "expectation_coverage",
        "actionability",
    ]
    assert "Be strict about structural compliance before style commentary." in captured["input"]
    assert "Set passed=true only if the answer is benchmark-worthy." in captured["input"]
    assert "failure_modes" in captured["input"]
    assert result.judge_name == "codex"
    assert result.passed is True
    assert result.dimensions[0].name == "task_fit"
    assert result.metadata["schema_enforced"] is True
