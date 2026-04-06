"""Benchmark execution entities and case resolution."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from .catalog import (
    BenchmarkCase,
    BenchmarkKind,
    BenchmarkMode,
    BenchmarkSuite,
    JudgePolicy,
    RuleEvaluationPolicy,
    load_case,
    load_suite_for_case,
)


@dataclass(frozen=True, slots=True)
class ExecutionPolicy:
    """Execution policy for running one benchmark case."""

    name: str
    use_temp_cwd: bool
    copy_repo_to_temp: bool
    setting_sources: tuple[str, ...]
    allowed_tools: tuple[str, ...]
    max_turns: int | None
    timeout_seconds: float | None


BUILTIN_EXECUTION_POLICIES: dict[str, ExecutionPolicy] = {
    "isolated_prompt": ExecutionPolicy(
        name="isolated_prompt",
        use_temp_cwd=True,
        copy_repo_to_temp=True,
        setting_sources=("project", "local"),
        allowed_tools=(),
        max_turns=1,
        timeout_seconds=180.0,
    ),
    "isolated_repo_copy": ExecutionPolicy(
        name="isolated_repo_copy",
        use_temp_cwd=False,
        copy_repo_to_temp=True,
        setting_sources=("project", "local"),
        allowed_tools=(),
        max_turns=1,
        timeout_seconds=180.0,
    ),
}


@dataclass(slots=True)
class SkillBindingStatus:
    """Normalized summary of one run's skill binding state."""

    requested_skills: list[str] = field(default_factory=list)
    injected_skills: list[str] = field(default_factory=list)
    registered_skills: list[str] = field(default_factory=list)
    registration_status: str = "not_requested"
    registration_confirmed: bool | None = None
    registration_evidence: str | None = None
    usage_confirmed: bool | None = None

    def to_dict(self) -> dict[str, object]:
        """Convert the summary into JSON-serializable data."""

        return {
            "requested_skills": list(self.requested_skills),
            "injected_skills": list(self.injected_skills),
            "registered_skills": list(self.registered_skills),
            "registration_status": self.registration_status,
            "registration_confirmed": self.registration_confirmed,
            "registration_evidence": self.registration_evidence,
            "usage_confirmed": self.usage_confirmed,
        }


@dataclass(slots=True)
class ResolvedCase:
    """Fully resolved benchmark case ready for execution."""

    suite: BenchmarkSuite
    case: BenchmarkCase
    execution_policy: ExecutionPolicy
    skill_paths: list[Path] = field(default_factory=list)
    rule_policy: RuleEvaluationPolicy | None = None
    judge_policy: JudgePolicy | None = None

    @property
    def id(self) -> str:
        """Return the case id."""

        return self.case.id

    @property
    def suite_id(self) -> str:
        """Return the suite id."""

        return self.suite.suite_id

    @property
    def mode(self) -> BenchmarkMode:
        """Return the case mode."""

        return self.case.mode

    @property
    def kind(self) -> BenchmarkKind:
        """Return the case kind."""

        return self.case.kind

    @property
    def source_path(self) -> Path | None:
        """Return the case source path."""

        return self.case.source_path

    def render_prompt(self) -> str:
        """Render the full prompt for execution."""

        if self.suite.prompt_contract is not None:
            return self.suite.prompt_contract.render(self.case)
        return self.case.render_prompt()

    def resolve_working_dir(self) -> Path | None:
        """Return the working directory for repo-aware cases."""

        return self.case.resolve_working_dir()


@dataclass(slots=True)
class BenchmarkRun:
    """Normalized record for one executed benchmark case."""

    case_id: str
    suite_id: str
    candidate_runtime_name: str
    mode: str
    kind: str
    execution_policy: str
    output_text: str
    duration_seconds: float
    metadata: dict[str, str | int | float | bool] = field(default_factory=dict)
    skill_binding: SkillBindingStatus = field(default_factory=SkillBindingStatus)
    rule_assessment: object | None = None
    judge_assessment: object | None = None
    rule_policy: str | None = None
    skill_paths: list[str] = field(default_factory=list)
    source_path: Path | None = None

    def to_dict(self) -> dict[str, object]:
        """Convert a run result into a JSON-serializable mapping."""

        return {
            "case_id": self.case_id,
            "suite_id": self.suite_id,
            "candidate_runtime_name": self.candidate_runtime_name,
            "mode": self.mode,
            "kind": self.kind,
            "execution_policy": self.execution_policy,
            "rule_policy": self.rule_policy,
            "skill_paths": list(self.skill_paths),
            "output_text": self.output_text,
            "duration_seconds": self.duration_seconds,
            "metadata": dict(self.metadata),
            "skill_binding": self.skill_binding.to_dict(),
            "rule_assessment": (
                self.rule_assessment.to_dict() if self.rule_assessment is not None else None
            ),
            "judge_assessment": (
                self.judge_assessment.to_dict() if self.judge_assessment is not None else None
            ),
            "source_path": str(self.source_path) if self.source_path else None,
        }


def get_execution_policy(name: str) -> ExecutionPolicy:
    """Return a built-in execution policy by name."""

    try:
        return BUILTIN_EXECUTION_POLICIES[name]
    except KeyError as exc:
        available = ", ".join(sorted(BUILTIN_EXECUTION_POLICIES))
        raise ValueError(f"Unknown execution policy {name!r}. Available: {available}") from exc


def resolve_case(
    path: str | Path,
    *,
    skill_paths: list[Path] | None = None,
    no_skills: bool = False,
    execution_policy_name: str | None = None,
    rule_policy_name: str | None = None,
    judge_policy_name: str | None = None,
) -> ResolvedCase:
    """Resolve suite defaults and case data into one executable case."""

    case = load_case(path)
    suite = load_suite_for_case(path)
    selected_execution_policy = (
        execution_policy_name or case.execution_policy_name or suite.default_execution_policy
    )
    execution_policy = get_execution_policy(selected_execution_policy)
    selected_rule_policy = rule_policy_name or case.rule_policy_name or suite.default_rule_policy
    selected_judge_policy = judge_policy_name or case.judge_policy_name or suite.default_judge_policy

    resolved_skill_paths: list[Path]
    if no_skills:
        resolved_skill_paths = []
    elif skill_paths:
        resolved_skill_paths = [path.resolve() for path in skill_paths]
    else:
        resolved_skill_paths = suite.resolve_default_skills()

    if case.skill_paths:
        resolved_skill_paths.extend(case.resolve_skill_paths())

    return ResolvedCase(
        suite=suite,
        case=case,
        execution_policy=execution_policy,
        skill_paths=resolved_skill_paths,
        rule_policy=suite.resolve_rule_policy(selected_rule_policy),
        judge_policy=suite.resolve_judge_policy(selected_judge_policy),
    )
