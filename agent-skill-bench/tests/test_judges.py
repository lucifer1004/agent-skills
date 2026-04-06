"""Judge runtime tests."""

from agent_skill_bench import (
    BenchmarkCase,
    BenchmarkMode,
    BenchmarkService,
    BenchmarkSuite,
    EvaluationCheck,
    JudgeTask,
    MockAgentRuntime,
    ResolvedCase,
    RuleAssessment,
    default_judge_policy,
    get_execution_policy,
    get_runtime,
)


def test_get_runtime_returns_mock_runtime_for_judging():
    runtime = get_runtime("mock")

    assert isinstance(runtime, MockAgentRuntime)


def test_mock_runtime_uses_rule_assessment_to_score_dimensions():
    case = ResolvedCase(
        suite=BenchmarkSuite(
            schema_version=1,
            suite_id="uiux",
            title="UIUX",
            default_execution_policy="isolated_prompt",
        ),
        case=BenchmarkCase(
            schema_version=1,
            id="uiux.generate.sample",
            title="Sample",
            mode=BenchmarkMode.GENERATE,
            prompt="Generate a page.",
        ),
        execution_policy=get_execution_policy("isolated_prompt"),
    )
    rule_assessment = RuleAssessment(
        policy="uiux-default",
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

    judge_result = BenchmarkService(
        MockAgentRuntime(),
        judge_runtime=MockAgentRuntime(),
    ).run_judge(
        JudgeTask(
            case=case,
            candidate_output="hello",
            rule_assessment=rule_assessment,
            judge_policy=default_judge_policy(),
        )
    )

    assert judge_result.judge_runtime_name == "mock"
    assert judge_result.passed is False
    assert [dimension.name for dimension in judge_result.dimensions] == [
        "contract_adherence",
        "rule_adherence",
    ]
    assert judge_result.dimensions[0].score == 1
    assert judge_result.dimensions[1].score == 3
