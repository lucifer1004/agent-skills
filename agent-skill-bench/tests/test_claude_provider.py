"""Claude Agent SDK provider tests."""

from __future__ import annotations

import asyncio
from pathlib import Path
from types import SimpleNamespace

from agent_skill_bench.fixtures import (
    BenchmarkCase,
    BenchmarkMode,
    BenchmarkSuite,
    ResolvedBenchmarkCase,
    get_execution_profile,
)
from agent_skill_bench.providers.claude import ClaudeAgentSDKProvider
import agent_skill_bench.providers.claude as claude_provider_module


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


def test_claude_provider_prefers_result_over_assistant_text(monkeypatch):
    case = ResolvedBenchmarkCase(
        suite=BenchmarkSuite(
            schema_version=1,
            suite_id="uiux",
            title="UIUX",
            default_execution_profile="isolated_prompt",
        ),
        case=BenchmarkCase(
            schema_version=1,
            id="uiux.generate.claude-provider",
            title="Claude Case",
            mode=BenchmarkMode.GENERATE,
            prompt="Design a dashboard.",
        ),
        execution_profile=get_execution_profile("isolated_prompt"),
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
    monkeypatch.setattr(claude_provider_module, "_import_claude_agent_sdk", lambda: fake_sdk)

    provider = ClaudeAgentSDKProvider(
        system_prompt="You are a reviewer",
        max_turns=2,
        isolate_home=True,
    )
    response = provider.run_case(case)

    assert captured["prompt"] == "Design a dashboard."
    assert captured["options"]["system_prompt"] == "You are a reviewer"
    assert captured["options"]["max_turns"] == 2
    assert captured["options"]["tools"] == []
    assert captured["options"]["extra_args"] == {
        "strict-mcp-config": None,
    }
    assert captured["options"]["setting_sources"] == ["project", "local"]
    assert captured["cwd_exists_during_run"] is True
    assert captured["home_exists_during_run"] is True
    assert callable(captured["options"]["stderr"])
    assert response.output_text == "final result"
    assert response.metadata["case_id"] == "uiux.generate.claude-provider"
    assert response.metadata["suite_id"] == "uiux"
    assert response.metadata["message_count"] == 3
    assert response.metadata["assistant_message_count"] == 1
    assert response.metadata["assistant_text_chars"] == len("first\nsecond")
    assert response.metadata["result_text_chars"] == len("final result")
    assert response.metadata["final_output_source"] == "result"
    assert response.metadata["profile"] == "isolated_prompt"
    assert response.metadata["available_skills"] == "uiux"
    assert response.metadata["available_slash_commands"] == "uiux,review"


def test_claude_provider_falls_back_to_assistant_text_without_result(monkeypatch):
    case = ResolvedBenchmarkCase(
        suite=BenchmarkSuite(
            schema_version=1,
            suite_id="uiux",
            title="UIUX",
            default_execution_profile="isolated_prompt",
        ),
        case=BenchmarkCase(
            schema_version=1,
            id="uiux.generate.assistant-fallback",
            title="Claude Fallback Case",
            mode=BenchmarkMode.GENERATE,
            prompt="Design a settings page.",
        ),
        execution_profile=get_execution_profile("isolated_prompt"),
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
    monkeypatch.setattr(claude_provider_module, "_import_claude_agent_sdk", lambda: fake_sdk)

    response = ClaudeAgentSDKProvider().run_case(case)

    assert response.output_text == "section one\nsection two"
    assert response.metadata["assistant_message_count"] == 1
    assert response.metadata["assistant_text_chars"] == len("section one\nsection two")
    assert response.metadata["result_text_chars"] == 0
    assert response.metadata["final_output_source"] == "assistant_fallback"


def test_claude_provider_times_out(monkeypatch):
    case = ResolvedBenchmarkCase(
        suite=BenchmarkSuite(
            schema_version=1,
            suite_id="uiux",
            title="UIUX",
            default_execution_profile="isolated_prompt",
        ),
        case=BenchmarkCase(
            schema_version=1,
            id="uiux.generate.claude-timeout",
            title="Claude Timeout Case",
            mode=BenchmarkMode.GENERATE,
            prompt="Design a dashboard.",
        ),
        execution_profile=get_execution_profile("isolated_prompt"),
    )

    class FakeOptions:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

    async def fake_query(*, prompt, options):
        await asyncio.sleep(0.05)
        if False:  # pragma: no cover - keeps this an async generator
            yield None

    fake_sdk = SimpleNamespace(
        ClaudeAgentOptions=FakeOptions,
        AssistantMessage=FakeAssistantMessage,
        SystemMessage=FakeSystemMessage,
        TextBlock=FakeTextBlock,
        query=fake_query,
    )
    monkeypatch.setattr(claude_provider_module, "_import_claude_agent_sdk", lambda: fake_sdk)

    provider = ClaudeAgentSDKProvider(timeout_seconds=0.01)

    try:
        provider.run_case(case)
    except RuntimeError as exc:
        assert "timed out" in str(exc)
        assert case.id in str(exc)
    else:  # pragma: no cover - defensive
        raise AssertionError("Expected Claude provider to time out.")


def test_claude_provider_copies_repo_case_to_temp(monkeypatch, tmp_path: Path):
    repo_root = tmp_path / "fixture-repo"
    app_dir = repo_root / "app"
    app_dir.mkdir(parents=True)
    (app_dir / "README.md").write_text("benchmark repo", encoding="utf-8")

    case = ResolvedBenchmarkCase(
        suite=BenchmarkSuite(
            schema_version=1,
            suite_id="uiux",
            title="UIUX",
            default_execution_profile="isolated_repo_copy",
        ),
        case=BenchmarkCase(
            schema_version=1,
            id="uiux.adapt.repo-copy",
            title="Repo Case",
            mode=BenchmarkMode.ADAPT,
            prompt="Adapt this UI.",
            repo_path="fixture-repo",
            cwd="app",
            source_path=tmp_path / "case.json",
        ),
        execution_profile=get_execution_profile("isolated_repo_copy"),
    )

    captured: dict[str, object] = {}

    class FakeOptions:
        def __init__(self, **kwargs):
            captured["options"] = kwargs
            self.__dict__.update(kwargs)

    async def fake_query(*, prompt, options):
        captured["prompt"] = prompt
        captured["cwd_exists_during_run"] = Path(options.cwd).is_dir()
        captured["copied_readme"] = (Path(options.cwd) / "README.md").read_text(
            encoding="utf-8"
        )
        yield FakeResultMessage("repo result")

    fake_sdk = SimpleNamespace(
        ClaudeAgentOptions=FakeOptions,
        AssistantMessage=FakeAssistantMessage,
        SystemMessage=FakeSystemMessage,
        TextBlock=FakeTextBlock,
        query=fake_query,
    )
    monkeypatch.setattr(claude_provider_module, "_import_claude_agent_sdk", lambda: fake_sdk)

    provider = ClaudeAgentSDKProvider(isolate_home=True)
    response = provider.run_case(case)

    copied_cwd = Path(captured["options"]["cwd"])
    assert copied_cwd != app_dir
    assert copied_cwd.name == app_dir.name
    assert captured["cwd_exists_during_run"] is True
    assert captured["copied_readme"] == "benchmark repo"
    assert captured["options"]["setting_sources"] == ["project", "local"]
    assert captured["options"]["tools"] == []
    assert response.output_text == "repo result"


def test_claude_provider_injects_explicit_skills(monkeypatch, tmp_path: Path):
    fixture_skill = tmp_path / "fixture-skill"
    fixture_skill.mkdir()
    (fixture_skill / "SKILL.md").write_text("Fixture skill instructions", encoding="utf-8")
    (fixture_skill / "guide.md").write_text("fixture reference", encoding="utf-8")

    manual_skill = tmp_path / "manual-skill"
    manual_skill.mkdir()
    (manual_skill / "SKILL.md").write_text("Manual skill instructions", encoding="utf-8")

    case = ResolvedBenchmarkCase(
        suite=BenchmarkSuite(
            schema_version=1,
            suite_id="uiux",
            title="UIUX",
            default_execution_profile="isolated_prompt",
        ),
        case=BenchmarkCase(
            schema_version=1,
            id="uiux.generate.skill-injection",
            title="Injected Skill Case",
            mode=BenchmarkMode.GENERATE,
            prompt="Design a pricing page.",
        ),
        execution_profile=get_execution_profile("isolated_prompt"),
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
    monkeypatch.setattr(claude_provider_module, "_import_claude_agent_sdk", lambda: fake_sdk)

    provider = ClaudeAgentSDKProvider()
    response = provider.run_case(case)

    assert captured["fixture_skill_text"] == "Fixture skill instructions"
    assert captured["fixture_skill_asset"] == "fixture reference"
    assert captured["manual_skill_text"] == "Manual skill instructions"
    assert response.metadata["injected_skill_count"] == 2
    assert response.metadata["injected_skills"] == "manual-skill,fixture-skill"
    assert response.metadata["registered_injected_skills"] == "manual-skill,fixture-skill"
    assert response.metadata["registered_injected_skill_count"] == 2
