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
    reevaluate_run_artifact,
    save_run_results,
)
from agent_skill_bench.infrastructure.agent_runtime import (
    AgentRunResult,
    AgentRunSpec,
    AgentRuntimeError,
)


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
    assert result.candidate_outcome.status == "succeeded"
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
    assert payload[0]["candidate_outcome"]["status"] == "succeeded"
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


def test_service_marks_native_codex_skill_materialization(tmp_path: Path):
    skill_dir = tmp_path / "uiux"
    skill_dir.mkdir()
    (skill_dir / "SKILL.md").write_text("UIUX skill", encoding="utf-8")

    @dataclass
    class NativeCodexRuntime:
        name: str = "codex"

        def run(self, spec: AgentRunSpec) -> AgentRunResult:
            return AgentRunResult(
                output_text="handled",
                metadata={
                    "injected_skills": "uiux",
                    "skill_binding_mode": "native_codex_home",
                    "skill_binding_evidence": "runtime_metadata.codex_home_skills",
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
            id="uiux.generate.native-codex-skill",
            title="Native Codex Skill",
            mode=BenchmarkMode.GENERATE,
            prompt="Generate a page.",
        ),
        execution_policy=get_execution_policy("isolated_prompt"),
        skill_paths=[skill_dir],
    )

    result = BenchmarkService(NativeCodexRuntime()).run_case(case)

    assert result.skill_binding.requested_skills == ["uiux"]
    assert result.skill_binding.injected_skills == ["uiux"]
    assert result.skill_binding.registered_skills == []
    assert result.skill_binding.registration_status == "materialized"
    assert result.skill_binding.registration_confirmed is None
    assert result.skill_binding.registration_evidence == "runtime_metadata.codex_home_skills"
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
    assert result.judge_outcome is not None
    assert result.judge_outcome.status == "succeeded"
    assert result.judge_assessment.metadata["case_mode"] == "Review"


def test_service_persists_failed_candidate_run_as_artifact():
    @dataclass
    class FailingRuntime:
        name: str = "codex"

        def run(self, spec: AgentRunSpec) -> AgentRunResult:
            raise AgentRuntimeError("runtime_timeout", "Candidate runtime timed out.")

    case = ResolvedCase(
        suite=BenchmarkSuite(
            schema_version=1,
            suite_id="uiux",
            title="UIUX",
            default_execution_policy="isolated_prompt",
        ),
        case=BenchmarkCase(
            schema_version=1,
            id="uiux.generate.failed",
            title="Failed Sample",
            mode=BenchmarkMode.GENERATE,
            prompt="Generate a page.",
        ),
        execution_policy=get_execution_policy("isolated_prompt"),
    )

    result = BenchmarkService(FailingRuntime()).run_case(case)

    assert result.output_text == ""
    assert result.candidate_outcome.status == "failed"
    assert result.candidate_outcome.code == "runtime_timeout"
    assert result.rule_assessment is None
    assert result.judge_assessment is None


def test_service_records_failed_judge_outcome_without_dropping_candidate_result():
    @dataclass
    class FailingJudgeRuntime:
        name: str = "claude"

        def run(self, spec: AgentRunSpec) -> AgentRunResult:
            if spec.purpose == "candidate":
                return AgentRunResult(output_text="## Screen Goal\n\nGoal\n\n## Layout Blocks\n\nBlocks")
            raise AgentRuntimeError(
                "structured_output_mismatch",
                "Judge output did not satisfy the required schema.",
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
            id="uiux.generate.failed-judge",
            title="Judge Failure",
            mode=BenchmarkMode.GENERATE,
            prompt="Generate a page.",
        ),
        execution_policy=get_execution_policy("isolated_prompt"),
    )

    result = BenchmarkService(FailingJudgeRuntime(), judge_runtime=FailingJudgeRuntime()).run_case(case)

    assert result.candidate_outcome.status == "succeeded"
    assert result.rule_assessment is not None
    assert result.judge_assessment is None
    assert result.judge_outcome is not None
    assert result.judge_outcome.code == "structured_output_mismatch"


def test_reevaluate_run_artifact_recomputes_rule_assessment_from_saved_output(tmp_path: Path):
    suite_dir = tmp_path / "agent-skill-uiux" / "benchmarks"
    case_dir = suite_dir / "cases"
    suite_dir.mkdir(parents=True)
    case_dir.mkdir()
    (suite_dir / "suite.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "suite_id": "uiux",
                "title": "UIUX Suite",
                "default_execution_policy": "isolated_prompt",
                "default_rule_policy": "uiux-default",
                "rule_policies": {
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
                "prompt_contract": {
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
                "id": "uiux.generate.reevaluate",
                "title": "Reevaluate Case",
                "mode": "Generate",
                "prompt": "Design a dashboard.",
                "expectations": {
                    "must_cover": [],
                    "must_avoid": [],
                    "golden_signals": []
                }
            }
        ),
        encoding="utf-8",
    )

    record = {
        "case_id": "uiux.generate.reevaluate",
        "suite_id": "uiux",
        "candidate_runtime_name": "mock",
        "mode": "Generate",
        "kind": "prompt",
        "execution_policy": "isolated_prompt",
        "rule_policy": "uiux-default",
        "skill_paths": [],
        "output_text": "## Screen Goal\n\nGoal\n\n## Layout Blocks\n\nBlocks",
        "duration_seconds": 1.2,
        "metadata": {},
        "skill_binding": {"requested_skills": [], "injected_skills": [], "registered_skills": [], "registration_status": "not_requested", "registration_confirmed": None, "registration_evidence": None, "usage_confirmed": None},
        "source_path": str(case),
    }

    reevaluated = reevaluate_run_artifact(record)

    assert reevaluated["candidate_outcome"]["status"] == "succeeded"
    assert reevaluated["rule_assessment"]["passed"] is True
    assert reevaluated["source_path"] == str(case)
