"""Judge tests."""

from agent_skill_bench import (
    BenchmarkCase,
    BenchmarkEvaluation,
    BenchmarkMode,
    BenchmarkRunner,
    BenchmarkSuite,
    EvaluationCheck,
    MockBenchmarkJudge,
    ResolvedBenchmarkCase,
    get_execution_profile,
    get_judge,
)
from agent_skill_bench.providers import ProviderRunResponse


def test_get_judge_returns_mock_judge():
    judge = get_judge("mock")

    assert isinstance(judge, MockBenchmarkJudge)


def test_mock_judge_uses_rule_evaluation_to_score_dimensions():
    case = ResolvedBenchmarkCase(
        suite=BenchmarkSuite(
            schema_version=1,
            suite_id="uiux",
            title="UIUX",
            default_execution_profile="isolated_prompt",
        ),
        case=BenchmarkCase(
            schema_version=1,
            id="uiux.generate.sample",
            title="Sample",
            mode=BenchmarkMode.GENERATE,
            prompt="Generate a page.",
        ),
        execution_profile=get_execution_profile("isolated_prompt"),
    )
    rule_evaluation = BenchmarkEvaluation(
        profile="uiux-default",
        passed=False,
        contract_checks=[
            EvaluationCheck(code="a", passed=True, message="ok"),
            EvaluationCheck(code="b", passed=False, message="bad"),
        ],
        rule_checks=[
            EvaluationCheck(code="c", passed=True, message="ok"),
        ],
        failure_modes=["b"],
    )

    judge_result = MockBenchmarkJudge().evaluate_case(
        case,
        output_text="hello",
        rule_evaluation=rule_evaluation,
    )

    assert judge_result.judge_name == "mock"
    assert judge_result.passed is False
    assert [dimension.name for dimension in judge_result.dimensions] == [
        "contract_adherence",
        "rule_adherence",
    ]
    assert judge_result.dimensions[0].score == 1
    assert judge_result.dimensions[1].score == 3

