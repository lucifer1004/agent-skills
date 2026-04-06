"""Codex CLI provider tests."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

from agent_skill_bench.fixtures import (
    BenchmarkCase,
    BenchmarkMode,
    BenchmarkSuite,
    ResolvedBenchmarkCase,
    get_execution_profile,
)
from agent_skill_bench.providers.codex import CodexCLIProvider
import agent_skill_bench.providers.codex as codex_provider_module


def test_codex_provider_reads_output_last_message_and_usage(monkeypatch, tmp_path: Path):
    case = ResolvedBenchmarkCase(
        suite=BenchmarkSuite(
            schema_version=1,
            suite_id="uiux",
            title="UIUX",
            default_execution_profile="isolated_prompt",
        ),
        case=BenchmarkCase(
            schema_version=1,
            id="uiux.generate.codex-provider",
            title="Codex Case",
            mode=BenchmarkMode.GENERATE,
            prompt="Design a dashboard.",
        ),
        execution_profile=get_execution_profile("isolated_prompt"),
    )

    captured: dict[str, object] = {}

    def fake_run(cmd, *, capture_output, text, timeout, env, input):
        captured["cmd"] = cmd
        captured["timeout"] = timeout
        captured["input"] = input
        output_path = Path(cmd[cmd.index("--output-last-message") + 1])
        output_path.write_text("final codex result", encoding="utf-8")
        stdout = "\n".join(
            [
                json.dumps({"type": "thread.started", "thread_id": "thread-123"}),
                json.dumps({"type": "turn.completed", "usage": {"input_tokens": 10, "output_tokens": 5}}),
            ]
        )
        return SimpleNamespace(returncode=0, stdout=stdout, stderr="")

    monkeypatch.setattr(codex_provider_module.subprocess, "run", fake_run)

    response = CodexCLIProvider(system_prompt="Be precise").run_case(case)

    assert captured["input"] == "Design a dashboard."
    assert captured["cmd"][:2] == ["codex", "exec"]
    assert "--json" in captured["cmd"]
    assert "--skip-git-repo-check" in captured["cmd"]
    assert response.output_text == "final codex result"
    assert response.metadata["thread_id"] == "thread-123"
    assert response.metadata["usage_input_tokens"] == 10
    assert response.metadata["usage_output_tokens"] == 5
    assert response.metadata["final_output_source"] == "output_last_message_file"


def test_codex_provider_materializes_skills_into_generated_agents(monkeypatch, tmp_path: Path):
    fixture_skill = tmp_path / "fixture-skill"
    fixture_skill.mkdir()
    (fixture_skill / "SKILL.md").write_text("Always use hierarchy first.", encoding="utf-8")
    (fixture_skill / "guide.md").write_text("extra guide", encoding="utf-8")

    case = ResolvedBenchmarkCase(
        suite=BenchmarkSuite(
            schema_version=1,
            suite_id="uiux",
            title="UIUX",
            default_execution_profile="isolated_prompt",
        ),
        case=BenchmarkCase(
            schema_version=1,
            id="uiux.generate.codex-skill",
            title="Codex Skill Case",
            mode=BenchmarkMode.GENERATE,
            prompt="Design a pricing page.",
        ),
        execution_profile=get_execution_profile("isolated_prompt"),
        skill_paths=[fixture_skill],
    )

    captured: dict[str, object] = {}

    def fake_run(cmd, *, capture_output, text, timeout, env, input):
        cwd = Path(cmd[cmd.index("--cd") + 1])
        captured["agents_text"] = (cwd / "AGENTS.md").read_text(encoding="utf-8")
        captured["skill_file_text"] = (
            cwd / ".agent-skill-bench" / "skills" / "fixture-skill" / "SKILL.md"
        ).read_text(encoding="utf-8")
        output_path = Path(cmd[cmd.index("--output-last-message") + 1])
        output_path.write_text("skill result", encoding="utf-8")
        return SimpleNamespace(
            returncode=0,
            stdout=json.dumps({"type": "turn.completed", "usage": {"input_tokens": 1}}),
            stderr="",
        )

    monkeypatch.setattr(codex_provider_module.subprocess, "run", fake_run)

    response = CodexCLIProvider().run_case(case)

    assert "Injected Benchmark Skills" in captured["agents_text"]
    assert "Always use hierarchy first." in captured["agents_text"]
    assert captured["skill_file_text"] == "Always use hierarchy first."
    assert response.metadata["injected_skills"] == "fixture-skill"
    assert response.metadata["skill_binding_mode"] == "workspace_agents"


def test_codex_provider_copies_repo_case_to_temp(monkeypatch, tmp_path: Path):
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
            id="uiux.adapt.codex-repo-copy",
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

    def fake_run(cmd, *, capture_output, text, timeout, env, input):
        cwd = Path(cmd[cmd.index("--cd") + 1])
        captured["cwd"] = cwd
        captured["copied_readme"] = (cwd / "README.md").read_text(encoding="utf-8")
        output_path = Path(cmd[cmd.index("--output-last-message") + 1])
        output_path.write_text("repo result", encoding="utf-8")
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(codex_provider_module.subprocess, "run", fake_run)

    response = CodexCLIProvider().run_case(case)

    assert captured["cwd"] != app_dir
    assert captured["cwd"].name == app_dir.name
    assert captured["copied_readme"] == "benchmark repo"
    assert response.output_text == "repo result"
