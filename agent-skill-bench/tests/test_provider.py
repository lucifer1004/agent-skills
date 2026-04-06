"""Provider tests."""

from pathlib import Path

from agent_skill_bench import BenchmarkCase, BenchmarkMode, BenchmarkSuite, ResolvedBenchmarkCase, get_execution_profile
from agent_skill_bench.providers import MockBenchmarkProvider, get_provider


def test_get_provider_returns_mock_provider():
    provider = get_provider("mock")

    assert isinstance(provider, MockBenchmarkProvider)


def test_mock_provider_returns_deterministic_output():
    case = ResolvedBenchmarkCase(
        suite=BenchmarkSuite(schema_version=1, suite_id="uiux", title="UIUX", default_execution_profile="isolated_prompt"),
        case=BenchmarkCase(
            schema_version=1,
            id="uiux.review.provider",
            title="Provider Case",
            mode=BenchmarkMode.REVIEW,
            prompt="Review this page.",
        ),
        execution_profile=get_execution_profile("isolated_prompt"),
        skill_paths=[Path("/tmp/uiux-skill")],
        evaluation_profile="uiux-default",
    )

    response = MockBenchmarkProvider().run_case(case)

    assert response.output_text == "[mock:Review] Review this page."
    assert response.metadata == {
        "case_id": "uiux.review.provider",
        "suite_id": "uiux",
        "kind": "prompt",
        "execution_profile": "isolated_prompt",
        "skill_count": 1,
    }
