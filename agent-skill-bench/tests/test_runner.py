"""Runner tests."""

from dataclasses import dataclass
import json
from pathlib import Path

from agent_skill_bench import BenchmarkCase, BenchmarkMode, BenchmarkRunner, BenchmarkSuite, ResolvedBenchmarkCase, get_execution_profile
from agent_skill_bench.providers import ProviderRunResponse
from agent_skill_bench.runners import save_run_results


@dataclass
class FakeProvider:
    name: str = "fake"

    def run_case(self, case: ResolvedBenchmarkCase) -> ProviderRunResponse:
        return ProviderRunResponse(
            output_text=f"handled:{case.id}",
            metadata={"mode": case.mode.value},
        )


def test_runner_normalizes_provider_output():
    case = ResolvedBenchmarkCase(
        suite=BenchmarkSuite(schema_version=1, suite_id="uiux", title="UIUX", default_execution_profile="isolated_prompt"),
        case=BenchmarkCase(
            schema_version=1,
            id="uiux.review.sample",
            title="Sample",
            mode=BenchmarkMode.REVIEW,
            prompt="Review this UI",
        ),
        execution_profile=get_execution_profile("isolated_prompt"),
    )

    result = BenchmarkRunner(FakeProvider()).run_case(case)

    assert result.case_id == "uiux.review.sample"
    assert result.suite_id == "uiux"
    assert result.provider_name == "fake"
    assert result.output_text == "handled:uiux.review.sample"
    assert result.metadata == {"mode": "Review"}
    assert result.mode == "Review"
    assert result.kind == "prompt"
    assert result.execution_profile == "isolated_prompt"
    assert result.skill_binding.registration_status == "not_requested"
    assert result.skill_binding.registration_confirmed is None
    assert result.evaluation is not None
    assert result.evaluation.profile is None
    assert result.duration_seconds >= 0


def test_save_run_results_persists_json(tmp_path: Path):
    case = ResolvedBenchmarkCase(
        suite=BenchmarkSuite(schema_version=1, suite_id="uiux", title="UIUX", default_execution_profile="isolated_prompt"),
        case=BenchmarkCase(
            schema_version=1,
            id="uiux.generate.sample",
            title="Sample",
            mode=BenchmarkMode.GENERATE,
            prompt="Generate a page.",
        ),
        execution_profile=get_execution_profile("isolated_prompt"),
    )
    result = BenchmarkRunner(FakeProvider()).run_case(case)

    output_path = tmp_path / "runs" / "result.json"
    saved_path = save_run_results([result], output_path)

    assert saved_path == output_path
    payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert payload[0]["case_id"] == "uiux.generate.sample"
    assert payload[0]["provider_name"] == "fake"
    assert payload[0]["skill_binding"]["registration_status"] == "not_requested"
    assert "evaluation" in payload[0]


def test_runner_marks_skill_registration_from_provider_metadata(tmp_path: Path):
    skill_dir = tmp_path / "uiux"
    skill_dir.mkdir()
    (skill_dir / "SKILL.md").write_text("UIUX skill", encoding="utf-8")

    @dataclass
    class SkillAwareProvider:
        name: str = "claude"

        def run_case(self, case: ResolvedBenchmarkCase) -> ProviderRunResponse:
            return ProviderRunResponse(
                output_text="handled",
                metadata={
                    "injected_skills": "uiux",
                    "registered_injected_skills": "uiux",
                },
            )

    case = ResolvedBenchmarkCase(
        suite=BenchmarkSuite(schema_version=1, suite_id="uiux", title="UIUX", default_execution_profile="isolated_prompt"),
        case=BenchmarkCase(
            schema_version=1,
            id="uiux.generate.registered-skill",
            title="Registered Skill",
            mode=BenchmarkMode.GENERATE,
            prompt="Generate a page.",
        ),
        execution_profile=get_execution_profile("isolated_prompt"),
        skill_paths=[skill_dir],
    )

    result = BenchmarkRunner(SkillAwareProvider()).run_case(case)

    assert result.skill_binding.requested_skills == ["uiux"]
    assert result.skill_binding.injected_skills == ["uiux"]
    assert result.skill_binding.registered_skills == ["uiux"]
    assert result.skill_binding.registration_status == "registered"
    assert result.skill_binding.registration_confirmed is True
    assert result.skill_binding.registration_evidence == "provider_metadata.cli_init"
    assert result.skill_binding.usage_confirmed is None
