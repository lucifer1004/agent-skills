"""Runtime registry and mock candidate tests."""

from pathlib import Path

from agent_skill_bench import (
    BenchmarkCase,
    BenchmarkMode,
    BenchmarkSuite,
    MockAgentRuntime,
    ResolvedCase,
    build_candidate_run_spec,
    get_execution_policy,
    get_runtime,
)
from agent_skill_bench.infrastructure.agent_runtime import CodexCLIAgentRuntime


def test_get_runtime_returns_mock_runtime():
    runtime = get_runtime("mock")

    assert isinstance(runtime, MockAgentRuntime)


def test_get_runtime_returns_codex_runtime():
    runtime = get_runtime("codex")

    assert isinstance(runtime, CodexCLIAgentRuntime)


def test_mock_runtime_returns_deterministic_candidate_output():
    case = ResolvedCase(
        suite=BenchmarkSuite(
            schema_version=1,
            suite_id="uiux",
            title="UIUX",
            default_execution_policy="isolated_prompt",
        ),
        case=BenchmarkCase(
            schema_version=1,
            id="uiux.review.runtime",
            title="Runtime Case",
            mode=BenchmarkMode.REVIEW,
            prompt="Review this page.",
        ),
        execution_policy=get_execution_policy("isolated_prompt"),
        skill_paths=[Path("/tmp/uiux-skill")],
    )

    response = MockAgentRuntime().run(build_candidate_run_spec(case))

    assert response.output_text == "[mock:Review] Review this page."
    assert response.metadata == {
        "case_id": "uiux.review.runtime",
        "suite_id": "uiux",
        "case_mode": "Review",
        "kind": "prompt",
        "execution_policy": "isolated_prompt",
    }
