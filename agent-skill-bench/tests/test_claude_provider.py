"""Claude SDK runtime tests."""

from __future__ import annotations

import asyncio
from pathlib import Path
from types import SimpleNamespace

from agent_skill_bench import (
    BenchmarkCase,
    BenchmarkMode,
    BenchmarkService,
    BenchmarkSuite,
    ClaudeSDKAgentRuntime,
    EvaluationCheck,
    JudgeTask,
    RepoTarget,
    ResolvedCase,
    RuleAssessment,
    build_candidate_run_spec,
    default_judge_policy,
    get_execution_policy,
)
import agent_skill_bench.infrastructure.agent_runtime.claude_sdk as claude_runtime_module


class FakeTextBlock:
    def __init__(self, text: str):
        self.text = text


class FakeAssistantMessage:
    def __init__(self, *content: FakeTextBlock):
        self.content = list(content)


class FakeResultMessage:
    def __init__(self, result: str):
        self.result = result


class FakeSystemMessage:
    def __init__(self, subtype: str, data: dict[str, object]):
        self.subtype = subtype
        self.data = data


def test_claude_runtime_prefers_result_over_assistant_text(monkeypatch):
    case = ResolvedCase(
        suite=BenchmarkSuite(
            schema_version=1,
            suite_id="uiux",
            title="UIUX",
            default_execution_policy="isolated_prompt",
        ),
        case=BenchmarkCase(
            schema_version=1,
            id="uiux.generate.claude-runtime",
            title="Claude Case",
            mode=BenchmarkMode.GENERATE,
            prompt="Design a dashboard.",
        ),
        execution_policy=get_execution_policy("isolated_prompt"),
    )

    captured: dict[str, object] = {}

    class FakeOptions:
        def __init__(self, **kwargs):
            captured["options"] = kwargs
            self.__dict__.update(kwargs)

    async def fake_query(*, prompt, options):
        captured["prompt"] = prompt
        captured["cwd_exists_during_run"] = Path(options.cwd).is_dir()
        captured["home_exists_during_run"] = Path(options.env["HOME"]).is_dir()
        yield FakeSystemMessage(
            "init",
            {
                "skills": ["uiux"],
                "slash_commands": ["uiux", "review"],
            },
        )
        yield FakeAssistantMessage(FakeTextBlock("first"), FakeTextBlock("second"))
        yield FakeResultMessage("final result")

    fake_sdk = SimpleNamespace(
        ClaudeAgentOptions=FakeOptions,
        AssistantMessage=FakeAssistantMessage,
        SystemMessage=FakeSystemMessage,
        TextBlock=FakeTextBlock,
        query=fake_query,
    )
    monkeypatch.setattr(claude_runtime_module, "_import_claude_agent_sdk", lambda: fake_sdk)

    runtime = ClaudeSDKAgentRuntime(
        instructions="You are a reviewer",
        max_turns=2,
        isolate_home=True,
    )
    response = runtime.run(build_candidate_run_spec(case))

    assert captured["prompt"] == "Design a dashboard."
    assert "You are a reviewer" in captured["options"]["system_prompt"]
    assert captured["options"]["max_turns"] == 2
    assert captured["options"]["tools"] == []
    assert captured["options"]["extra_args"] == {"strict-mcp-config": None}
    assert captured["options"]["setting_sources"] == ["project", "local"]
    assert captured["cwd_exists_during_run"] is True
    assert captured["home_exists_during_run"] is True
    assert callable(captured["options"]["stderr"])
    assert response.output_text == "final result"
    assert response.metadata["case_id"] == "uiux.generate.claude-runtime"
    assert response.metadata["suite_id"] == "uiux"
    assert response.metadata["message_count"] == 3
    assert response.metadata["assistant_message_count"] == 1
    assert response.metadata["assistant_text_chars"] == len("first\nsecond")
    assert response.metadata["result_text_chars"] == len("final result")
    assert response.metadata["final_output_source"] == "result"
    assert response.metadata["execution_policy"] == "isolated_prompt"
    assert response.metadata["available_skills"] == "uiux"
    assert response.metadata["available_slash_commands"] == "uiux,review"


def test_claude_runtime_falls_back_to_assistant_text_without_result(monkeypatch):
    case = ResolvedCase(
        suite=BenchmarkSuite(
            schema_version=1,
            suite_id="uiux",
            title="UIUX",
            default_execution_policy="isolated_prompt",
        ),
        case=BenchmarkCase(
            schema_version=1,
            id="uiux.generate.assistant-fallback",
            title="Claude Fallback Case",
            mode=BenchmarkMode.GENERATE,
            prompt="Design a settings page.",
        ),
        execution_policy=get_execution_policy("isolated_prompt"),
    )

    class FakeOptions:
        def __init__(self, **kwargs):
            self.__dict__.update(kwargs)

    async def fake_query(*, prompt, options):
        yield FakeAssistantMessage(FakeTextBlock("section one"), FakeTextBlock("section two"))

    fake_sdk = SimpleNamespace(
        ClaudeAgentOptions=FakeOptions,
        AssistantMessage=FakeAssistantMessage,
        SystemMessage=FakeSystemMessage,
        TextBlock=FakeTextBlock,
        query=fake_query,
    )
    monkeypatch.setattr(claude_runtime_module, "_import_claude_agent_sdk", lambda: fake_sdk)

    response = ClaudeSDKAgentRuntime().run(build_candidate_run_spec(case))

    assert response.output_text == "section one\nsection two"
    assert response.metadata["assistant_message_count"] == 1
    assert response.metadata["assistant_text_chars"] == len("section one\nsection two")
    assert response.metadata["result_text_chars"] == 0
    assert response.metadata["final_output_source"] == "assistant_fallback"


def test_claude_runtime_times_out(monkeypatch):
    case = ResolvedCase(
        suite=BenchmarkSuite(
            schema_version=1,
            suite_id="uiux",
            title="UIUX",
            default_execution_policy="isolated_prompt",
        ),
        case=BenchmarkCase(
            schema_version=1,
            id="uiux.generate.claude-timeout",
            title="Claude Timeout Case",
            mode=BenchmarkMode.GENERATE,
            prompt="Design a dashboard.",
        ),
        execution_policy=get_execution_policy("isolated_prompt"),
    )

    class FakeOptions:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

    async def fake_query(*, prompt, options):
        await asyncio.sleep(0.05)
        if False:  # pragma: no cover
            yield None

    fake_sdk = SimpleNamespace(
        ClaudeAgentOptions=FakeOptions,
        AssistantMessage=FakeAssistantMessage,
        SystemMessage=FakeSystemMessage,
        TextBlock=FakeTextBlock,
        query=fake_query,
    )
    monkeypatch.setattr(claude_runtime_module, "_import_claude_agent_sdk", lambda: fake_sdk)

    runtime = ClaudeSDKAgentRuntime(timeout_seconds=0.01)

    try:
        runtime.run(build_candidate_run_spec(case))
    except RuntimeError as exc:
        assert "timed out" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("Expected Claude runtime to time out.")


def test_claude_runtime_copies_repo_case_to_temp(monkeypatch, tmp_path: Path):
    repo_root = tmp_path / "fixture-repo"
    app_dir = repo_root / "app"
    app_dir.mkdir(parents=True)
    (app_dir / "README.md").write_text("benchmark repo", encoding="utf-8")

    case = ResolvedCase(
        suite=BenchmarkSuite(
            schema_version=1,
            suite_id="uiux",
            title="UIUX",
            default_execution_policy="isolated_repo_copy",
        ),
        case=BenchmarkCase(
            schema_version=1,
            id="uiux.adapt.repo-copy",
            title="Repo Case",
            mode=BenchmarkMode.ADAPT,
            prompt="Adapt this UI.",
            repo_target=RepoTarget(path="fixture-repo", working_dir="app"),
            source_path=tmp_path / "case.json",
        ),
        execution_policy=get_execution_policy("isolated_repo_copy"),
    )

    captured: dict[str, object] = {}

    class FakeOptions:
        def __init__(self, **kwargs):
            captured["options"] = kwargs
            self.__dict__.update(kwargs)

    async def fake_query(*, prompt, options):
        captured["prompt"] = prompt
        captured["cwd_exists_during_run"] = Path(options.cwd).is_dir()
        captured["copied_readme"] = (Path(options.cwd) / "README.md").read_text(encoding="utf-8")
        yield FakeResultMessage("repo result")

    fake_sdk = SimpleNamespace(
        ClaudeAgentOptions=FakeOptions,
        AssistantMessage=FakeAssistantMessage,
        SystemMessage=FakeSystemMessage,
        TextBlock=FakeTextBlock,
        query=fake_query,
    )
    monkeypatch.setattr(claude_runtime_module, "_import_claude_agent_sdk", lambda: fake_sdk)

    runtime = ClaudeSDKAgentRuntime(isolate_home=True)
    response = runtime.run(build_candidate_run_spec(case))

    copied_cwd = Path(captured["options"]["cwd"])
    assert copied_cwd != app_dir
    assert copied_cwd.name == app_dir.name
    assert captured["cwd_exists_during_run"] is True
    assert captured["copied_readme"] == "benchmark repo"
    assert captured["options"]["setting_sources"] == ["project", "local"]
    assert captured["options"]["tools"] == []
    assert response.output_text == "repo result"


def test_claude_runtime_injects_explicit_skills(monkeypatch, tmp_path: Path):
    fixture_skill = tmp_path / "fixture-skill"
    fixture_skill.mkdir()
    (fixture_skill / "SKILL.md").write_text("Fixture skill instructions", encoding="utf-8")
    (fixture_skill / "guide.md").write_text("fixture reference", encoding="utf-8")

    manual_skill = tmp_path / "manual-skill"
    manual_skill.mkdir()
    (manual_skill / "SKILL.md").write_text("Manual skill instructions", encoding="utf-8")

    case = ResolvedCase(
        suite=BenchmarkSuite(
            schema_version=1,
            suite_id="uiux",
            title="UIUX",
            default_execution_policy="isolated_prompt",
        ),
        case=BenchmarkCase(
            schema_version=1,
            id="uiux.generate.skill-injection",
            title="Injected Skill Case",
            mode=BenchmarkMode.GENERATE,
            prompt="Design a pricing page.",
        ),
        execution_policy=get_execution_policy("isolated_prompt"),
        skill_paths=[manual_skill, fixture_skill / "SKILL.md"],
    )

    captured: dict[str, object] = {}

    class FakeOptions:
        def __init__(self, **kwargs):
            captured["options"] = kwargs
            self.__dict__.update(kwargs)

    async def fake_query(*, prompt, options):
        skills_root = Path(options.cwd) / ".claude" / "skills"
        captured["fixture_skill_text"] = (skills_root / "fixture-skill" / "SKILL.md").read_text(
            encoding="utf-8"
        )
        captured["fixture_skill_asset"] = (skills_root / "fixture-skill" / "guide.md").read_text(
            encoding="utf-8"
        )
        captured["manual_skill_text"] = (skills_root / "manual-skill" / "SKILL.md").read_text(
            encoding="utf-8"
        )
        yield FakeSystemMessage(
            "init",
            {
                "skills": ["manual-skill", "fixture-skill"],
                "slash_commands": ["manual-skill", "fixture-skill"],
            },
        )
        yield FakeResultMessage("skill result")

    fake_sdk = SimpleNamespace(
        ClaudeAgentOptions=FakeOptions,
        AssistantMessage=FakeAssistantMessage,
        SystemMessage=FakeSystemMessage,
        TextBlock=FakeTextBlock,
        query=fake_query,
    )
    monkeypatch.setattr(claude_runtime_module, "_import_claude_agent_sdk", lambda: fake_sdk)

    runtime = ClaudeSDKAgentRuntime()
    response = runtime.run(build_candidate_run_spec(case))

    assert captured["fixture_skill_text"] == "Fixture skill instructions"
    assert captured["fixture_skill_asset"] == "fixture reference"
    assert captured["manual_skill_text"] == "Manual skill instructions"
    assert response.metadata["injected_skill_count"] == 2
    assert response.metadata["injected_skills"] == "manual-skill,fixture-skill"
    assert response.metadata["registered_injected_skills"] == "manual-skill,fixture-skill"
    assert response.metadata["registered_injected_skill_count"] == 2


def test_claude_judge_runtime_accepts_fenced_canonical_json(monkeypatch):
    case = ResolvedCase(
        suite=BenchmarkSuite(
            schema_version=1,
            suite_id="uiux",
            title="UIUX",
            default_execution_policy="isolated_prompt",
        ),
        case=BenchmarkCase(
            schema_version=1,
            id="uiux.generate.claude-judge",
            title="Claude Judge Case",
            mode=BenchmarkMode.GENERATE,
            prompt="Design a dashboard.",
        ),
        execution_policy=get_execution_policy("isolated_prompt"),
    )
    rule_assessment = RuleAssessment(
        policy="uiux-default",
        passed=True,
        contract_checks=[EvaluationCheck(code="a", passed=True, message="ok")],
        rule_checks=[EvaluationCheck(code="b", passed=True, message="ok")],
        failure_modes=[],
    )

    class FakeOptions:
        def __init__(self, **kwargs):
            self.__dict__.update(kwargs)

    async def fake_query(*, prompt, options):
        yield FakeResultMessage(
            """```json
{
  "passed": true,
  "summary": "Strong answer.",
  "dimensions": [
    {"name": "task_fit", "score": 3, "rationale": "Fits task."},
    {"name": "contract_adherence", "score": 3, "rationale": "Matches contract."},
    {"name": "expectation_coverage", "score": 2, "rationale": "Mostly covers expectations."},
    {"name": "actionability", "score": 3, "rationale": "Actionable."}
  ]
}
```"""
        )

    fake_sdk = SimpleNamespace(
        ClaudeAgentOptions=FakeOptions,
        AssistantMessage=FakeAssistantMessage,
        SystemMessage=FakeSystemMessage,
        TextBlock=FakeTextBlock,
        query=fake_query,
    )
    monkeypatch.setattr(claude_runtime_module, "_import_claude_agent_sdk", lambda: fake_sdk)

    result = BenchmarkService(
        ClaudeSDKAgentRuntime(),
        judge_runtime=ClaudeSDKAgentRuntime(),
    ).run_judge(
        JudgeTask(
            case=case,
            candidate_output="candidate output",
            rule_assessment=rule_assessment,
            judge_policy=default_judge_policy(),
        )
    )

    assert result.judge_runtime_name == "claude"
    assert result.passed is True
    assert [dimension.name for dimension in result.dimensions] == [
        "task_fit",
        "contract_adherence",
        "expectation_coverage",
        "actionability",
    ]


def test_claude_judge_runtime_rejects_non_canonical_json(monkeypatch):
    case = ResolvedCase(
        suite=BenchmarkSuite(
            schema_version=1,
            suite_id="uiux",
            title="UIUX",
            default_execution_policy="isolated_prompt",
        ),
        case=BenchmarkCase(
            schema_version=1,
            id="uiux.generate.bad-judge-shape",
            title="Bad Judge Shape",
            mode=BenchmarkMode.GENERATE,
            prompt="Design a dashboard.",
        ),
        execution_policy=get_execution_policy("isolated_prompt"),
    )

    class FakeOptions:
        def __init__(self, **kwargs):
            self.__dict__.update(kwargs)

    async def fake_query(*, prompt, options):
        yield FakeResultMessage(
            """```json
{
  "task_fit": 3,
  "contract_adherence": 2,
  "expectation_coverage": 3,
  "actionability": 3,
  "passed": true,
  "reasoning": "wrong shape"
}
```"""
        )

    fake_sdk = SimpleNamespace(
        ClaudeAgentOptions=FakeOptions,
        AssistantMessage=FakeAssistantMessage,
        SystemMessage=FakeSystemMessage,
        TextBlock=FakeTextBlock,
        query=fake_query,
    )
    monkeypatch.setattr(claude_runtime_module, "_import_claude_agent_sdk", lambda: fake_sdk)

    try:
        BenchmarkService(
            ClaudeSDKAgentRuntime(),
            judge_runtime=ClaudeSDKAgentRuntime(),
        ).run_judge(
            JudgeTask(
                case=case,
                candidate_output="candidate output",
                rule_assessment=None,
                judge_policy=default_judge_policy(),
            )
        )
    except RuntimeError as exc:
        assert "required" in str(exc) or "unexpected properties" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("Expected non-canonical judge JSON to be rejected.")
