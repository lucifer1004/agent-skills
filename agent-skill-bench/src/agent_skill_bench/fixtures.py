"""Suite, case, and execution-profile models for benchmark runs."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
import json
from pathlib import Path


class BenchmarkMode(StrEnum):
    """Supported benchmark task modes."""

    GENERATE = "Generate"
    REVIEW = "Review"
    ADAPT = "Adapt"
    IMPLEMENT_HANDOFF = "Implement-Handoff"


class BenchmarkKind(StrEnum):
    """Execution shapes for benchmark cases."""

    PROMPT = "prompt"
    REPO = "repo"


class EvaluationRuleKind(StrEnum):
    """Supported generic rule kinds for rule-based evaluation."""

    SECTION_NON_EMPTY = "section_non_empty"
    SECTION_MATCHES_REGEX = "section_matches_regex"
    SECTION_CONTAINS_LIST_ITEM = "section_contains_list_item"
    OUTPUT_NOT_MATCHES_REGEX = "output_not_matches_regex"


@dataclass(slots=True)
class BenchmarkExpectations:
    """Evaluation expectations for one benchmark case."""

    must_cover: list[str] = field(default_factory=list)
    must_avoid: list[str] = field(default_factory=list)
    golden_signals: list[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: dict[str, object] | None) -> "BenchmarkExpectations":
        """Build expectations from JSON data."""

        payload = data or {}
        if not isinstance(payload, dict):
            raise ValueError("Case field 'expectations' must be an object.")
        return cls(
            must_cover=_string_list(payload.get("must_cover", []), "expectations.must_cover"),
            must_avoid=_string_list(payload.get("must_avoid", []), "expectations.must_avoid"),
            golden_signals=_string_list(
                payload.get("golden_signals", []),
                "expectations.golden_signals",
            ),
        )

    def to_dict(self) -> dict[str, list[str]]:
        """Convert expectations into JSON-serializable data."""

        return {
            "must_cover": list(self.must_cover),
            "must_avoid": list(self.must_avoid),
            "golden_signals": list(self.golden_signals),
        }


@dataclass(slots=True)
class BenchmarkPromptContract:
    """Suite-level prompt scaffolding for consistent benchmark execution."""

    preamble: list[str] = field(default_factory=list)
    shared_rules: list[str] = field(default_factory=list)
    mode_headings: dict[BenchmarkMode, list[str]] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: dict[str, object] | None) -> "BenchmarkPromptContract | None":
        """Build a prompt contract from JSON data when present."""

        if data is None:
            return None
        if not isinstance(data, dict):
            raise ValueError("Suite field 'benchmark_prompt' must be an object.")

        mode_headings_raw = _optional_dict(
            data.get("mode_headings"),
            "benchmark_prompt.mode_headings",
        ) or {}
        mode_headings: dict[BenchmarkMode, list[str]] = {}
        for key, value in mode_headings_raw.items():
            mode_headings[BenchmarkMode(str(key))] = _string_list(
                value,
                f"benchmark_prompt.mode_headings.{key}",
            )

        return cls(
            preamble=_string_list(data.get("preamble", []), "benchmark_prompt.preamble"),
            shared_rules=_string_list(
                data.get("shared_rules", []),
                "benchmark_prompt.shared_rules",
            ),
            mode_headings=mode_headings,
        )

    def render(self, case: "BenchmarkCase") -> str:
        """Render a benchmark prompt around the user request."""

        sections: list[str] = []
        if self.preamble:
            sections.append("\n".join(self.preamble))

        sections.append("User Request:")
        sections.append(case.prompt)

        if case.context or case.context_files:
            sections.append("Context Notes:")
            sections.extend(f"- {line}" for line in case.context)
            for path in case.resolve_context_paths():
                sections.append(f"Context File: {path}")
                sections.append(path.read_text(encoding="utf-8"))

        if self.shared_rules:
            sections.append("Benchmark Rules:")
            sections.extend(f"- {rule}" for rule in self.shared_rules)

        mode_headings = self.mode_headings.get(case.mode, [])
        if mode_headings:
            sections.append(f"Required Output Headings ({case.mode.value}):")
            sections.extend(f"- {heading}" for heading in mode_headings)

        sections.append("Return only the final answer.")
        return "\n\n".join(section for section in sections if section)


@dataclass(slots=True)
class BenchmarkEvaluationRule:
    """Declarative rule definition owned by one benchmark suite."""

    code: str
    kind: EvaluationRuleKind
    message: str
    section: str | None = None
    pattern: str | None = None

    @classmethod
    def from_dict(cls, data: dict[str, object], *, field_name: str) -> "BenchmarkEvaluationRule":
        """Build one declarative evaluation rule from JSON data."""

        required = ("code", "kind", "message")
        missing = [key for key in required if key not in data]
        if missing:
            raise ValueError(f"{field_name} is missing required keys: {', '.join(missing)}")

        kind = EvaluationRuleKind(str(data["kind"]))
        section = _optional_string(data.get("section"), f"{field_name}.section")
        pattern = _optional_string(data.get("pattern"), f"{field_name}.pattern")

        if kind in {
            EvaluationRuleKind.SECTION_NON_EMPTY,
            EvaluationRuleKind.SECTION_MATCHES_REGEX,
            EvaluationRuleKind.SECTION_CONTAINS_LIST_ITEM,
        } and section is None:
            raise ValueError(f"{field_name} requires 'section'.")
        if kind in {
            EvaluationRuleKind.SECTION_MATCHES_REGEX,
            EvaluationRuleKind.OUTPUT_NOT_MATCHES_REGEX,
        } and pattern is None:
            raise ValueError(f"{field_name} requires 'pattern'.")

        return cls(
            code=str(data["code"]),
            kind=kind,
            message=str(data["message"]),
            section=section,
            pattern=pattern,
        )


@dataclass(slots=True)
class BenchmarkEvaluationProfile:
    """Suite-local rule set selected by a case or suite default."""

    name: str
    forbid_code_fences: bool = True
    require_first_heading: bool = True
    mode_rules: dict[BenchmarkMode, list[BenchmarkEvaluationRule]] = field(default_factory=dict)

    @classmethod
    def from_dict(
        cls,
        name: str,
        data: dict[str, object],
        *,
        field_name: str,
    ) -> "BenchmarkEvaluationProfile":
        """Build one evaluation profile from JSON data."""

        mode_rules_raw = _optional_dict(data.get("mode_rules"), f"{field_name}.mode_rules") or {}
        mode_rules: dict[BenchmarkMode, list[BenchmarkEvaluationRule]] = {}
        for mode_name, raw_rules in mode_rules_raw.items():
            rule_items = _list_of_dicts(raw_rules, f"{field_name}.mode_rules.{mode_name}")
            mode_rules[BenchmarkMode(str(mode_name))] = [
                BenchmarkEvaluationRule.from_dict(
                    rule,
                    field_name=f"{field_name}.mode_rules.{mode_name}[{index}]",
                )
                for index, rule in enumerate(rule_items)
            ]

        return cls(
            name=name,
            forbid_code_fences=_optional_bool(data.get("forbid_code_fences"), f"{field_name}.forbid_code_fences", default=True),
            require_first_heading=_optional_bool(data.get("require_first_heading"), f"{field_name}.require_first_heading", default=True),
            mode_rules=mode_rules,
        )


@dataclass(slots=True)
class BenchmarkCase:
    """Canonical case definition for one benchmark task."""

    schema_version: int
    id: str
    title: str
    mode: BenchmarkMode
    prompt: str
    expectations: BenchmarkExpectations = field(default_factory=BenchmarkExpectations)
    context: list[str] = field(default_factory=list)
    context_files: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    repo_path: str | None = None
    cwd: str | None = None
    execution_profile: str | None = None
    evaluation_profile: str | None = None
    skill_paths: list[str] = field(default_factory=list)
    source_path: Path | None = None

    @property
    def kind(self) -> BenchmarkKind:
        """Return the effective execution kind for the case."""

        return BenchmarkKind.REPO if self.repo_path is not None else BenchmarkKind.PROMPT

    @classmethod
    def from_dict(cls, data: dict[str, object], *, source_path: Path | None = None) -> "BenchmarkCase":
        """Build and validate a benchmark case from JSON data."""

        required = ("schema_version", "id", "title", "mode", "prompt", "expectations")
        missing = [key for key in required if key not in data]
        if missing:
            raise ValueError(f"Case is missing required keys: {', '.join(missing)}")

        repo_path = _optional_string(data.get("repo_path"), "repo_path")
        cwd = _optional_string(data.get("cwd"), "cwd")
        if cwd is not None and repo_path is None:
            raise ValueError("Case field 'cwd' requires 'repo_path'.")

        return cls(
            schema_version=int(data["schema_version"]),
            id=str(data["id"]),
            title=str(data["title"]),
            mode=BenchmarkMode(str(data["mode"])),
            prompt=str(data["prompt"]),
            expectations=BenchmarkExpectations.from_dict(_dict_value(data.get("expectations"), "expectations")),
            context=_string_list(data.get("context", []), "context"),
            context_files=_string_list(data.get("context_files", []), "context_files"),
            tags=_string_list(data.get("tags", []), "tags"),
            repo_path=repo_path,
            cwd=cwd,
            execution_profile=_optional_string(data.get("execution_profile"), "execution_profile"),
            evaluation_profile=_optional_string(data.get("evaluation_profile"), "evaluation_profile"),
            skill_paths=_string_list(data.get("skill_paths", []), "skill_paths"),
            source_path=source_path,
        )

    def render_prompt(self) -> str:
        """Render the prompt with all attached context."""

        if not self.context and not self.context_files:
            return self.prompt

        sections = [self.prompt]
        if self.context:
            sections.append("Context Notes:")
            sections.extend(f"- {line}" for line in self.context)

        for path in self.resolve_context_paths():
            sections.append(f"Context File: {path}")
            sections.append(path.read_text(encoding="utf-8"))

        return "\n\n".join(sections)

    def resolve_context_paths(self) -> list[Path]:
        """Resolve attached context file paths relative to the case file."""

        if self.source_path is None:
            raise ValueError("Cannot resolve context paths without source_path.")
        base_dir = self.source_path.parent
        return [_resolve_path(base_dir, relative_path) for relative_path in self.context_files]

    def resolve_skill_paths(self) -> list[Path]:
        """Resolve case-local skill paths relative to the case file."""

        if self.source_path is None:
            raise ValueError("Cannot resolve skill paths without source_path.")
        base_dir = self.source_path.parent
        return [_resolve_path(base_dir, relative_path) for relative_path in self.skill_paths]

    def resolve_repo_root(self) -> Path | None:
        """Resolve the repo root for repo-aware cases."""

        if self.repo_path is None:
            return None
        if self.source_path is None:
            raise ValueError("Cannot resolve repo paths without source_path.")
        return _resolve_path(self.source_path.parent, self.repo_path)

    def resolve_working_dir(self) -> Path | None:
        """Resolve the effective working directory for repo-aware cases."""

        repo_root = self.resolve_repo_root()
        if repo_root is None:
            return None
        if self.cwd is None:
            return repo_root
        return (repo_root / self.cwd).resolve()


@dataclass(slots=True)
class BenchmarkSuite:
    """Suite-level defaults shared by many benchmark cases."""

    schema_version: int
    suite_id: str
    title: str
    default_skills: list[str] = field(default_factory=list)
    default_execution_profile: str = "isolated_prompt"
    default_evaluation_profile: str | None = None
    evaluation_profiles: dict[str, BenchmarkEvaluationProfile] = field(default_factory=dict)
    benchmark_prompt: BenchmarkPromptContract | None = None
    source_path: Path | None = None

    @classmethod
    def from_dict(cls, data: dict[str, object], *, source_path: Path | None = None) -> "BenchmarkSuite":
        """Build and validate a benchmark suite manifest."""

        required = (
            "schema_version",
            "suite_id",
            "title",
            "default_execution_profile",
        )
        missing = [key for key in required if key not in data]
        if missing:
            raise ValueError(f"Suite manifest is missing required keys: {', '.join(missing)}")

        return cls(
            schema_version=int(data["schema_version"]),
            suite_id=str(data["suite_id"]),
            title=str(data["title"]),
            default_skills=_string_list(data.get("default_skills", []), "default_skills"),
            default_execution_profile=str(data["default_execution_profile"]),
            default_evaluation_profile=_optional_string(
                data.get("default_evaluation_profile"),
                "default_evaluation_profile",
            ),
            evaluation_profiles=_evaluation_profiles(
                _optional_dict(data.get("evaluation_profiles"), "evaluation_profiles") or {}
            ),
            benchmark_prompt=BenchmarkPromptContract.from_dict(
                _optional_dict(data.get("benchmark_prompt"), "benchmark_prompt")
            ),
            source_path=source_path,
        )

    def resolve_default_skills(self) -> list[Path]:
        """Resolve suite-default skill paths relative to the suite manifest."""

        if self.source_path is None:
            raise ValueError("Cannot resolve suite skills without source_path.")
        base_dir = self.source_path.parent
        return [_resolve_path(base_dir, relative_path) for relative_path in self.default_skills]

    def resolve_evaluation_profile(
        self,
        name: str | None,
    ) -> BenchmarkEvaluationProfile | None:
        """Resolve an evaluation profile from suite-local definitions."""

        if name is None:
            return None
        try:
            return self.evaluation_profiles[name]
        except KeyError as exc:
            available = ", ".join(sorted(self.evaluation_profiles)) or "<none>"
            raise ValueError(
                f"Unknown evaluation profile {name!r} for suite {self.suite_id!r}. Available: {available}"
            ) from exc


@dataclass(frozen=True, slots=True)
class ExecutionProfile:
    """Execution policy for running one benchmark case."""

    name: str
    use_temp_cwd: bool
    copy_repo_to_temp: bool
    setting_sources: tuple[str, ...]
    allowed_tools: tuple[str, ...]
    max_turns: int | None
    timeout_seconds: float | None


BUILTIN_EXECUTION_PROFILES: dict[str, ExecutionProfile] = {
    "isolated_prompt": ExecutionProfile(
        name="isolated_prompt",
        use_temp_cwd=True,
        copy_repo_to_temp=True,
        setting_sources=("project", "local"),
        allowed_tools=(),
        max_turns=1,
        timeout_seconds=180.0,
    ),
    "isolated_repo_copy": ExecutionProfile(
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
class ResolvedBenchmarkCase:
    """Fully resolved benchmark case ready for provider execution."""

    suite: BenchmarkSuite
    case: BenchmarkCase
    execution_profile: ExecutionProfile
    skill_paths: list[Path] = field(default_factory=list)
    evaluation_profile: str | None = None

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

        if self.suite.benchmark_prompt is not None:
            return self.suite.benchmark_prompt.render(self.case)
        return self.case.render_prompt()

    def resolve_working_dir(self) -> Path | None:
        """Return the working directory for repo-aware cases."""

        return self.case.resolve_working_dir()


def get_execution_profile(name: str) -> ExecutionProfile:
    """Return a built-in execution profile by name."""

    try:
        return BUILTIN_EXECUTION_PROFILES[name]
    except KeyError as exc:
        available = ", ".join(sorted(BUILTIN_EXECUTION_PROFILES))
        raise ValueError(f"Unknown execution profile {name!r}. Available: {available}") from exc


def load_case(path: str | Path) -> BenchmarkCase:
    """Load one benchmark case from JSON."""

    case_path = Path(path)
    data = json.loads(case_path.read_text(encoding="utf-8"))
    return BenchmarkCase.from_dict(_dict_value(data, "case"), source_path=case_path)


def load_suite(path: str | Path) -> BenchmarkSuite:
    """Load one suite manifest from JSON."""

    suite_path = Path(path)
    data = json.loads(suite_path.read_text(encoding="utf-8"))
    return BenchmarkSuite.from_dict(_dict_value(data, "suite manifest"), source_path=suite_path)


def load_suite_for_case(case_path: str | Path) -> BenchmarkSuite:
    """Load the suite manifest that owns a case file."""

    case_file = Path(case_path)
    suite_path = case_file.parent.parent / "suite.json"
    if not suite_path.is_file():
        raise FileNotFoundError(f"Missing suite manifest for case {case_file}: {suite_path}")
    return load_suite(suite_path)


def resolve_case(
    path: str | Path,
    *,
    skill_paths: list[Path] | None = None,
    no_skills: bool = False,
    execution_profile_name: str | None = None,
) -> ResolvedBenchmarkCase:
    """Resolve suite defaults and case data into one executable case."""

    case = load_case(path)
    suite = load_suite_for_case(path)
    profile_name = execution_profile_name or case.execution_profile or suite.default_execution_profile
    execution_profile = get_execution_profile(profile_name)
    evaluation_profile = case.evaluation_profile or suite.default_evaluation_profile

    resolved_skill_paths: list[Path]
    if no_skills:
        resolved_skill_paths = []
    elif skill_paths:
        resolved_skill_paths = [path.resolve() for path in skill_paths]
    else:
        resolved_skill_paths = suite.resolve_default_skills()

    if case.skill_paths:
        resolved_skill_paths.extend(case.resolve_skill_paths())

    return ResolvedBenchmarkCase(
        suite=suite,
        case=case,
        execution_profile=execution_profile,
        skill_paths=resolved_skill_paths,
        evaluation_profile=evaluation_profile,
    )


def _string_list(value: object, field_name: str) -> list[str]:
    """Validate list[str] fields with a useful error."""

    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise ValueError(f"Field {field_name!r} must be a list of strings.")
    return list(value)


def _optional_string(value: object, field_name: str) -> str | None:
    """Validate optional string fields."""

    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError(f"Field {field_name!r} must be a string when present.")
    return value


def _dict_value(value: object, field_name: str) -> dict[str, object]:
    """Validate object fields."""

    if not isinstance(value, dict):
        raise ValueError(f"{field_name.capitalize()} must be a JSON object.")
    return dict(value)


def _optional_dict(value: object, field_name: str) -> dict[str, object] | None:
    """Validate optional object fields."""

    if value is None:
        return None
    return _dict_value(value, field_name)


def _optional_bool(value: object, field_name: str, *, default: bool) -> bool:
    """Validate optional boolean fields."""

    if value is None:
        return default
    if not isinstance(value, bool):
        raise ValueError(f"Field {field_name!r} must be a boolean when present.")
    return value


def _list_of_dicts(value: object, field_name: str) -> list[dict[str, object]]:
    """Validate list[object] where every element is a JSON object."""

    if not isinstance(value, list):
        raise ValueError(f"Field {field_name!r} must be a list.")
    items: list[dict[str, object]] = []
    for index, item in enumerate(value):
        items.append(_dict_value(item, f"{field_name}[{index}]"))
    return items


def _evaluation_profiles(value: dict[str, object]) -> dict[str, BenchmarkEvaluationProfile]:
    """Parse suite-local evaluation profile definitions."""

    profiles: dict[str, BenchmarkEvaluationProfile] = {}
    for name, payload in value.items():
        profiles[str(name)] = BenchmarkEvaluationProfile.from_dict(
            str(name),
            _dict_value(payload, f"evaluation_profiles.{name}"),
            field_name=f"evaluation_profiles.{name}",
        )
    return profiles


def _resolve_path(base_dir: Path, path_value: str) -> Path:
    """Resolve an absolute or base-relative path."""

    path = Path(path_value)
    if not path.is_absolute():
        path = base_dir / path
    return path.resolve()
