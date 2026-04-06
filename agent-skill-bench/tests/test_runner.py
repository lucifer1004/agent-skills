"""Benchmark service tests."""

from dataclasses import dataclass
import json
from pathlib import Path

from agent_skill_bench import (
    BenchmarkCase,
    BenchmarkMode,
    BenchmarkService,
    BenchmarkSuite,
    MockAgentRuntime,
    ResolvedCase,
    get_execution_policy,
    save_run_results,
)
from agent_skill_bench.infrastructure.agent_runtime import AgentRunResult, AgentRunSpec


@dataclass
class FakeRuntime:
    name: str = "fake"

    def run(self, spec: AgentRunSpec) -> AgentRunResult:
        if spec.purpose == "candidate":
            return AgentRunResult(
                output_text=f"handled:{spec.metadata['case_id']}",
                metadata={"mode": str(spec.metadata["case_mode"])},
            )
        return AgentRunResult(
            output_text=json.dumps(
                {
                    "passed": True,
                    "summary": "judged",
                    "dimensions": [
                        {"name": "contract_adherence", "score": 3, "rationale": "ok"},
                    ],
                }
            ),
            parsed_output={
                "passed": True,
                "summary": "judged",
                "dimensions": [
                    {"name": "contract_adherence", "score": 3, "rationale": "ok"},
                ],
            },
            metadata={"case_mode": str(spec.metadata["case_mode"])},
        )


def test_service_normalizes_candidate_output():
    case = ResolvedCase(
        suite=BenchmarkSuite(
            schema_version=1,
            suite_id="uiux",
            title="UIUX",
            default_execution_policy="isolated_prompt",
        ),
        case=BenchmarkCase(
            schema_version=1,
            id="uiux.review.sample",
            title="Sample",
            mode=BenchmarkMode.REVIEW,
            prompt="Review this UI",
        ),
        execution_policy=get_execution_policy("isolated_prompt"),
    )

    result = BenchmarkService(FakeRuntime()).run_case(case)

    assert result.case_id == "uiux.review.sample"
    assert result.suite_id == "uiux"
    assert result.candidate_runtime_name == "fake"
    assert result.output_text == "handled:uiux.review.sample"
    assert result.metadata == {"mode": "Review"}
    assert result.mode == "Review"
    assert result.kind == "prompt"
    assert result.execution_policy == "isolated_prompt"
    assert result.skill_binding.registration_status == "not_requested"
    assert result.skill_binding.registration_confirmed is None
    assert result.rule_assessment is not None
    assert result.rule_assessment.policy is None
    assert result.duration_seconds >= 0


def test_save_run_results_persists_json(tmp_path: Path):
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
    result = BenchmarkService(FakeRuntime()).run_case(case)

    output_path = tmp_path / "runs" / "result.json"
    saved_path = save_run_results([result], output_path)

    assert saved_path == output_path
    payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert payload[0]["case_id"] == "uiux.generate.sample"
    assert payload[0]["candidate_runtime_name"] == "fake"
    assert payload[0]["skill_binding"]["registration_status"] == "not_requested"
    assert "rule_assessment" in payload[0]


def test_service_marks_skill_registration_from_runtime_metadata(tmp_path: Path):
    skill_dir = tmp_path / "uiux"
    skill_dir.mkdir()
    (skill_dir / "SKILL.md").write_text("UIUX skill", encoding="utf-8")

    @dataclass
    class SkillAwareRuntime:
        name: str = "claude"

        def run(self, spec: AgentRunSpec) -> AgentRunResult:
            return AgentRunResult(
                output_text="handled",
                metadata={
                    "injected_skills": "uiux",
                    "registered_injected_skills": "uiux",
                },
            )

    case = ResolvedCase(
        suite=BenchmarkSuite(
            schema_version=1,
            suite_id="uiux",
            title="UIUX",
            default_execution_policy="isolated_prompt",
        ),
        case=BenchmarkCase(
            schema_version=1,
            id="uiux.generate.registered-skill",
            title="Registered Skill",
            mode=BenchmarkMode.GENERATE,
            prompt="Generate a page.",
        ),
        execution_policy=get_execution_policy("isolated_prompt"),
        skill_paths=[skill_dir],
    )

    result = BenchmarkService(SkillAwareRuntime()).run_case(case)

    assert result.skill_binding.requested_skills == ["uiux"]
    assert result.skill_binding.injected_skills == ["uiux"]
    assert result.skill_binding.registered_skills == ["uiux"]
    assert result.skill_binding.registration_status == "registered"
    assert result.skill_binding.registration_confirmed is True
    assert result.skill_binding.registration_evidence == "runtime_metadata.cli_init"
    assert result.skill_binding.usage_confirmed is None


def test_service_can_attach_judge_assessment():
    case = ResolvedCase(
        suite=BenchmarkSuite(
            schema_version=1,
            suite_id="uiux",
            title="UIUX",
            default_execution_policy="isolated_prompt",
        ),
        case=BenchmarkCase(
            schema_version=1,
            id="uiux.review.judged",
            title="Judged Sample",
            mode=BenchmarkMode.REVIEW,
            prompt="Review this UI",
        ),
        execution_policy=get_execution_policy("isolated_prompt"),
    )

    result = BenchmarkService(FakeRuntime(), judge_runtime=MockAgentRuntime()).run_case(case)

    assert result.judge_assessment is not None
    assert result.judge_assessment.judge_runtime_name == "mock"
    assert result.judge_assessment.metadata["case_mode"] == "Review"
