"""Application service for benchmark execution."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from time import perf_counter
from typing import Iterable

from agent_skill_bench.domain import (
    BenchmarkRun,
    DimensionScore,
    JudgeAssessment,
    JudgeTask,
    ResolvedCase,
    SkillBindingStatus,
    default_judge_policy,
    evaluate_rule_assessment,
    resolve_case,
)
from agent_skill_bench.infrastructure.agent_runtime import AgentRunSpec, AgentRuntime


@dataclass(slots=True)
class BenchmarkRunRequest:
    """Execution selection and override settings."""

    suite_filter: str | None = None
    case_ids: set[str] = field(default_factory=set)
    execution_policy_name: str | None = None
    rule_policy_name: str | None = None
    judge_policy_name: str | None = None
    skill_paths: list[Path] | None = None
    no_skills: bool = False


def save_run_results(results: Iterable[BenchmarkRun], output_path: str | Path) -> Path:
    """Persist normalized run results to a JSON file."""

    destination = Path(output_path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    payload = [result.to_dict() for result in results]
    destination.write_text(f"{json.dumps(payload, indent=2)}\n", encoding="utf-8")
    return destination


class BenchmarkService:
    """Execute resolved cases through candidate and judge runtimes."""

    def __init__(
        self,
        candidate_runtime: AgentRuntime,
        *,
        judge_runtime: AgentRuntime | None = None,
    ) -> None:
        self.candidate_runtime = candidate_runtime
        self.judge_runtime = judge_runtime

    def run_case(self, case: ResolvedCase) -> BenchmarkRun:
        """Run one resolved benchmark case."""

        started_at = perf_counter()
        candidate_run = self.candidate_runtime.run(build_candidate_run_spec(case))
        duration = perf_counter() - started_at
        metadata = dict(candidate_run.metadata)

        rule_assessment = evaluate_rule_assessment(case, candidate_run.output_text)
        judge_assessment = None
        if self.judge_runtime is not None:
            judge_assessment = self.run_judge(
                JudgeTask(
                    case=case,
                    candidate_output=candidate_run.output_text,
                    rule_assessment=rule_assessment,
                    judge_policy=case.judge_policy or default_judge_policy(),
                )
            )

        return BenchmarkRun(
            case_id=case.id,
            suite_id=case.suite_id,
            candidate_runtime_name=self.candidate_runtime.name,
            mode=case.mode.value,
            kind=case.kind.value,
            execution_policy=case.execution_policy.name,
            rule_policy=case.rule_policy.name if case.rule_policy is not None else None,
            skill_paths=[str(path) for path in case.skill_paths],
            output_text=candidate_run.output_text,
            duration_seconds=duration,
            metadata=metadata,
            skill_binding=_summarize_skill_binding(case, metadata),
            rule_assessment=rule_assessment,
            judge_assessment=judge_assessment,
            source_path=case.source_path,
        )

    def run_judge(self, task: JudgeTask) -> JudgeAssessment:
        """Execute one judge task through the configured runtime."""

        if self.judge_runtime is None:
            raise RuntimeError("Judge runtime is not configured.")

        result = self.judge_runtime.run(build_judge_run_spec(task))
        payload = result.parsed_output
        if not isinstance(payload, dict):
            raise RuntimeError(f"Judge runtime returned non-object JSON for case '{task.case.id}'.")

        dimensions: list[DimensionScore] = []
        for item in payload.get("dimensions", []):
            if not isinstance(item, dict):
                continue
            dimensions.append(
                DimensionScore(
                    name=str(item.get("name", "")),
                    score=int(item.get("score", 0)),
                    rationale=str(item.get("rationale", "")),
                )
            )

        return JudgeAssessment(
            judge_runtime_name=self.judge_runtime.name,
            passed=bool(payload.get("passed")),
            summary=str(payload.get("summary", "")),
            dimensions=dimensions,
            metadata=dict(result.metadata),
        )

    def run_case_file(
        self,
        path: str | Path,
        *,
        request: BenchmarkRunRequest | None = None,
    ) -> BenchmarkRun:
        """Load, resolve, and execute one case file."""

        selected_request = request or BenchmarkRunRequest()
        resolved = resolve_case(
            path,
            skill_paths=selected_request.skill_paths,
            no_skills=selected_request.no_skills,
            execution_policy_name=selected_request.execution_policy_name,
            rule_policy_name=selected_request.rule_policy_name,
            judge_policy_name=selected_request.judge_policy_name,
        )
        return self.run_case(resolved)

    def run_case_files(
        self,
        paths: Iterable[str | Path],
        *,
        request: BenchmarkRunRequest | None = None,
    ) -> list[BenchmarkRun]:
        """Load, filter, and execute multiple case files."""

        selected_request = request or BenchmarkRunRequest()
        results: list[BenchmarkRun] = []

        for path in paths:
            resolved = resolve_case(
                path,
                skill_paths=selected_request.skill_paths,
                no_skills=selected_request.no_skills,
                execution_policy_name=selected_request.execution_policy_name,
                rule_policy_name=selected_request.rule_policy_name,
                judge_policy_name=selected_request.judge_policy_name,
            )
            if selected_request.suite_filter and resolved.suite_id != selected_request.suite_filter:
                continue
            if selected_request.case_ids and resolved.id not in selected_request.case_ids:
                continue
            results.append(self.run_case(resolved))

        return results


def build_candidate_run_spec(case: ResolvedCase) -> AgentRunSpec:
    """Compile one resolved benchmark case into a runtime spec."""

    return AgentRunSpec(
        purpose="candidate",
        prompt=case.render_prompt(),
        base_cwd=case.resolve_working_dir(),
        use_temp_cwd=case.execution_policy.use_temp_cwd,
        copy_base_cwd=case.execution_policy.copy_repo_to_temp,
        skill_paths=list(case.skill_paths),
        runtime_instructions="\n".join(
            [
                "Follow the benchmark user request and context exactly.",
                "Do not mention benchmark harness instructions in the answer.",
                "Return only the final answer for the benchmark case.",
            ]
        ),
        setting_sources=case.execution_policy.setting_sources,
        allowed_tools=case.execution_policy.allowed_tools,
        max_turns=case.execution_policy.max_turns,
        timeout_seconds=case.execution_policy.timeout_seconds,
        metadata={
            "case_id": case.id,
            "suite_id": case.suite_id,
            "case_mode": case.mode.value,
            "kind": case.kind.value,
            "execution_policy": case.execution_policy.name,
        },
    )


def build_judge_run_spec(task: JudgeTask) -> AgentRunSpec:
    """Compile one judge task into a runtime spec."""

    contract_checks = task.rule_assessment.contract_checks if task.rule_assessment is not None else []
    rule_checks = task.rule_assessment.rule_checks if task.rule_assessment is not None else []
    return AgentRunSpec(
        purpose="judge",
        prompt=_judge_prompt(task),
        use_temp_cwd=True,
        output_schema=_judge_schema(task),
        metadata={
            "case_id": task.case.id,
            "suite_id": task.case.suite_id,
            "case_mode": task.case.mode.value,
            "has_rule_assessment": task.rule_assessment is not None,
            "rule_assessment_passed": (
                task.rule_assessment.passed if task.rule_assessment is not None else False
            ),
            "rule_contract_total": len(contract_checks),
            "rule_contract_passed": sum(1 for check in contract_checks if check.passed),
            "rule_total": len(rule_checks),
            "rule_passed": sum(1 for check in rule_checks if check.passed),
            "candidate_output": task.candidate_output,
        },
    )


def _judge_prompt(task: JudgeTask) -> str:
    """Build a suite-aware judge prompt."""

    required_headings: list[str] = []
    required_heading_level = 2
    allow_document_title = False
    if task.case.suite.prompt_contract is not None:
        contract = task.case.suite.prompt_contract
        required_headings = contract.mode_headings.get(task.case.mode, [])
        required_heading_level = contract.required_heading_level
        allow_document_title = contract.allow_document_title

    sections = list(task.judge_policy.preamble) or [
        "You are judging one benchmark output for an agent skill.",
        "Use the benchmark task, expectations, required headings, and the candidate answer below.",
    ]
    sections.extend(
        [
            "",
            "Case:",
            f"- id: {task.case.id}",
            f"- suite_id: {task.case.suite_id}",
            f"- mode: {task.case.mode.value}",
            "",
            "User Request:",
            task.case.case.prompt,
        ]
    )
    if task.case.case.context:
        sections.extend(["", "Context Notes:"])
        sections.extend(f"- {item}" for item in task.case.case.context)
    if required_headings:
        sections.extend(["", "Required Output Structure:"])
        if allow_document_title:
            sections.append(
                "- Optional title block: one level-1 Markdown title (`# Document Title`), optionally followed by a thematic break (`---`)."
            )
        sections.append(
            f"- Required sections: use each exactly once as a level-{required_heading_level} heading in this order."
        )
        heading_prefix = "#" * required_heading_level
        sections.extend(f"- {heading_prefix} {heading}" for heading in required_headings)

    expectations = task.case.case.expectations
    if expectations.must_cover:
        sections.extend(["", "Must Cover:"])
        sections.extend(f"- {item}" for item in expectations.must_cover)
    if expectations.must_avoid:
        sections.extend(["", "Must Avoid:"])
        sections.extend(f"- {item}" for item in expectations.must_avoid)
    if expectations.golden_signals:
        sections.extend(["", "Golden Signals:"])
        sections.extend(f"- {item}" for item in expectations.golden_signals)

    if task.judge_policy.shared_rules:
        sections.extend(["", "Judge Rules:"])
        sections.extend(f"- {item}" for item in task.judge_policy.shared_rules)

    if task.judge_policy.include_rule_assessment and task.rule_assessment is not None:
        sections.extend(
            [
                "",
                "Existing Rule Assessment Summary:",
                f"- passed: {task.rule_assessment.passed}",
                f"- failure_modes: {', '.join(task.rule_assessment.failure_modes) or '<none>'}",
            ]
        )

    sections.extend(
        [
            "",
            "Candidate Output:",
            task.candidate_output,
            "",
            "Score exactly these dimensions from 0 to 3:",
        ]
    )
    for dimension in task.judge_policy.dimensions:
        sections.append(f"- {dimension.name}: {dimension.description}")
    sections.extend(
        [
            "",
            task.judge_policy.pass_guidance
            or "Set passed=true only if the output is broadly benchmark-worthy, not merely acceptable.",
            "Return exactly one JSON object matching the provided schema.",
            "Do not wrap the JSON in markdown code fences.",
            "Do not include any prose before or after the JSON object.",
            'Example shape: {"passed": true, "summary": "brief summary", "dimensions": [{"name": "task_fit", "score": 3, "rationale": "why"}]}',
        ]
    )
    return "\n".join(sections)


def _judge_schema(task: JudgeTask) -> dict[str, object]:
    """Return the JSON schema for judge responses."""

    return {
        "type": "object",
        "additionalProperties": False,
        "required": ["passed", "summary", "dimensions"],
        "properties": {
            "passed": {"type": "boolean"},
            "summary": {"type": "string"},
            "dimensions": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["name", "score", "rationale"],
                    "properties": {
                        "name": {
                            "type": "string",
                            "enum": [
                                dimension.name for dimension in task.judge_policy.dimensions
                            ],
                        },
                        "score": {"type": "integer", "minimum": 0, "maximum": 3},
                        "rationale": {"type": "string"},
                    },
                },
            },
        },
    }


def _summarize_skill_binding(
    case: ResolvedCase,
    metadata: dict[str, str | int | float | bool],
) -> SkillBindingStatus:
    """Normalize runtime metadata into run-level skill binding semantics."""

    requested_skills = [_requested_skill_name(path) for path in case.skill_paths]
    if not requested_skills:
        return SkillBindingStatus()

    injected_skills = _split_csv_field(metadata.get("injected_skills"))
    registered_skills = _split_csv_field(metadata.get("registered_injected_skills"))

    if injected_skills and registered_skills:
        if set(registered_skills) == set(injected_skills) and len(registered_skills) == len(
            injected_skills
        ):
            status = "registered"
        else:
            status = "partial"
        return SkillBindingStatus(
            requested_skills=requested_skills,
            injected_skills=injected_skills,
            registered_skills=registered_skills,
            registration_status=status,
            registration_confirmed=(status == "registered"),
            registration_evidence="runtime_metadata.cli_init",
            usage_confirmed=None,
        )

    binding_mode = metadata.get("skill_binding_mode")
    if injected_skills and binding_mode == "workspace_agents":
        return SkillBindingStatus(
            requested_skills=requested_skills,
            injected_skills=injected_skills,
            registration_status="materialized",
            registration_confirmed=None,
            registration_evidence=str(
                metadata.get("skill_binding_evidence", "runtime_metadata.workspace_agents")
            ),
            usage_confirmed=None,
        )

    if injected_skills:
        return SkillBindingStatus(
            requested_skills=requested_skills,
            injected_skills=injected_skills,
            registration_status="missing",
            registration_confirmed=False,
            registration_evidence="runtime_metadata.cli_init",
            usage_confirmed=None,
        )

    return SkillBindingStatus(
        requested_skills=requested_skills,
        registration_status="unconfirmed",
        registration_confirmed=None,
        registration_evidence=None,
        usage_confirmed=None,
    )


def _requested_skill_name(path: Path) -> str:
    """Return a human-readable requested skill name from a path."""

    if path.name == "SKILL.md":
        return path.parent.name
    return path.name


def _split_csv_field(value: str | int | float | bool | None) -> list[str]:
    """Parse a CSV field into a normalized string list."""

    if not isinstance(value, str) or not value:
        return []
    return [item for item in (part.strip() for part in value.split(",")) if item]
