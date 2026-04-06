"""Benchmark catalog entities and loaders."""

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
    """Supported deterministic rule kinds."""

    SECTION_NON_EMPTY = "section_non_empty"
    SECTION_MATCHES_REGEX = "section_matches_regex"
    SECTION_CONTAINS_LIST_ITEM = "section_contains_list_item"
    OUTPUT_NOT_MATCHES_REGEX = "output_not_matches_regex"


@dataclass(slots=True)
class JudgeDimension:
    """One suite-owned judge dimension."""

    name: str
    description: str

    @classmethod
    def from_dict(cls, data: dict[str, object], *, field_name: str) -> "JudgeDimension":
        """Build one judge dimension from JSON data."""

        required = ("name", "description")
        missing = [key for key in required if key not in data]
        if missing:
            raise ValueError(f"{field_name} is missing required keys: {', '.join(missing)}")
        return cls(name=str(data["name"]), description=str(data["description"]))


@dataclass(slots=True)
class JudgePolicy:
    """Suite-owned configuration for judge execution."""

    name: str
    preamble: list[str] = field(default_factory=list)
    shared_rules: list[str] = field(default_factory=list)
    dimensions: list[JudgeDimension] = field(default_factory=list)
    pass_guidance: str | None = None
    include_rule_assessment: bool = True

    @classmethod
    def from_dict(
        cls,
        name: str,
        data: dict[str, object],
        *,
        field_name: str,
    ) -> "JudgePolicy":
        """Build one judge policy from JSON data."""

        dimension_items = _list_of_dicts(data.get("dimensions", []), f"{field_name}.dimensions")
        dimensions = [
            JudgeDimension.from_dict(item, field_name=f"{field_name}.dimensions[{index}]")
            for index, item in enumerate(dimension_items)
        ]
        if not dimensions:
            raise ValueError(f"{field_name} must define at least one dimension.")

        return cls(
            name=name,
            preamble=_string_list(data.get("preamble", []), f"{field_name}.preamble"),
            shared_rules=_string_list(data.get("shared_rules", []), f"{field_name}.shared_rules"),
            dimensions=dimensions,
            pass_guidance=_optional_string(data.get("pass_guidance"), f"{field_name}.pass_guidance"),
            include_rule_assessment=_optional_bool(
                data.get("include_rule_assessment"),
                f"{field_name}.include_rule_assessment",
                default=True,
            ),
        )


@dataclass(slots=True)
class ExpectationSet:
    """Evaluation expectations for one benchmark case."""

    must_cover: list[str] = field(default_factory=list)
    must_avoid: list[str] = field(default_factory=list)
    golden_signals: list[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: dict[str, object] | None) -> "ExpectationSet":
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
class PromptContract:
    """Suite-level prompt scaffolding for consistent benchmark execution."""

    preamble: list[str] = field(default_factory=list)
    shared_rules: list[str] = field(default_factory=list)
    required_heading_level: int = 2
    allow_document_title: bool = True
    mode_headings: dict[BenchmarkMode, list[str]] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: dict[str, object] | None) -> "PromptContract | None":
        """Build a prompt contract from JSON data when present."""

        if data is None:
            return None
        if not isinstance(data, dict):
            raise ValueError("Suite field 'prompt_contract' must be an object.")

        mode_headings_raw = _optional_dict(
            data.get("mode_headings"),
            "prompt_contract.mode_headings",
        ) or {}
        mode_headings: dict[BenchmarkMode, list[str]] = {}
        for key, value in mode_headings_raw.items():
            mode_headings[BenchmarkMode(str(key))] = _string_list(
                value,
                f"prompt_contract.mode_headings.{key}",
            )

        return cls(
            preamble=_string_list(data.get("preamble", []), "prompt_contract.preamble"),
            shared_rules=_string_list(data.get("shared_rules", []), "prompt_contract.shared_rules"),
            required_heading_level=_optional_int(
                data.get("required_heading_level"),
                "prompt_contract.required_heading_level",
                default=2,
                minimum=1,
                maximum=6,
            ),
            allow_document_title=_optional_bool(
                data.get("allow_document_title"),
                "prompt_contract.allow_document_title",
                default=True,
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
            if self.allow_document_title:
                sections.append(
                    "- Optional title block: one level-1 Markdown title (`# Document Title`), optionally followed by a thematic break (`---`)."
                )
            sections.append(
                f"- Use each required section exactly once as a level-{self.required_heading_level} heading in this order."
            )
            heading_prefix = "#" * self.required_heading_level
            sections.extend(f"- {heading_prefix} {heading}" for heading in mode_headings)

        sections.append("Return only the final answer.")
        return "\n\n".join(section for section in sections if section)


@dataclass(slots=True)
class EvaluationRule:
    """Declarative deterministic rule definition owned by one suite."""

    code: str
    kind: EvaluationRuleKind
    message: str
    section: str | None = None
    pattern: str | None = None

    @classmethod
    def from_dict(cls, data: dict[str, object], *, field_name: str) -> "EvaluationRule":
        """Build one deterministic rule from JSON data."""

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
class RuleEvaluationPolicy:
    """Suite-local deterministic rule set."""

    name: str
    forbid_code_fences: bool = True
    require_first_heading: bool = True
    mode_rules: dict[BenchmarkMode, list[EvaluationRule]] = field(default_factory=dict)

    @classmethod
    def from_dict(
        cls,
        name: str,
        data: dict[str, object],
        *,
        field_name: str,
    ) -> "RuleEvaluationPolicy":
        """Build one rule evaluation policy from JSON data."""

        mode_rules_raw = _optional_dict(data.get("mode_rules"), f"{field_name}.mode_rules") or {}
        mode_rules: dict[BenchmarkMode, list[EvaluationRule]] = {}
        for mode_name, raw_rules in mode_rules_raw.items():
            rule_items = _list_of_dicts(raw_rules, f"{field_name}.mode_rules.{mode_name}")
            mode_rules[BenchmarkMode(str(mode_name))] = [
                EvaluationRule.from_dict(
                    rule,
                    field_name=f"{field_name}.mode_rules.{mode_name}[{index}]",
                )
                for index, rule in enumerate(rule_items)
            ]

        return cls(
            name=name,
            forbid_code_fences=_optional_bool(
                data.get("forbid_code_fences"),
                f"{field_name}.forbid_code_fences",
                default=True,
            ),
            require_first_heading=_optional_bool(
                data.get("require_first_heading"),
                f"{field_name}.require_first_heading",
                default=True,
            ),
            mode_rules=mode_rules,
        )


@dataclass(slots=True)
class RepoTarget:
    """Repository-relative execution target for repo-aware cases."""

    path: str
    working_dir: str | None = None

    @classmethod
    def from_dict(cls, data: dict[str, object], *, field_name: str) -> "RepoTarget":
        """Build one repo target from JSON data."""

        path = _optional_string(data.get("path"), f"{field_name}.path")
        working_dir = _optional_string(data.get("working_dir"), f"{field_name}.working_dir")
        if path is None:
            raise ValueError(f"{field_name} requires 'path'.")
        return cls(path=path, working_dir=working_dir)

    def resolve_root(self, base_dir: Path) -> Path:
        """Resolve the repo root relative to a case file."""

        return _resolve_path(base_dir, self.path)

    def resolve_working_dir_path(self, base_dir: Path) -> Path:
        """Resolve the effective working directory."""

        repo_root = self.resolve_root(base_dir)
        if self.working_dir is None:
            return repo_root
        return (repo_root / self.working_dir).resolve()


@dataclass(slots=True)
class BenchmarkCase:
    """Canonical case definition for one benchmark task."""

    schema_version: int
    id: str
    title: str
    mode: BenchmarkMode
    prompt: str
    expectations: ExpectationSet = field(default_factory=ExpectationSet)
    context: list[str] = field(default_factory=list)
    context_files: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    repo_target: RepoTarget | None = None
    execution_policy_name: str | None = None
    rule_policy_name: str | None = None
    judge_policy_name: str | None = None
    skill_paths: list[str] = field(default_factory=list)
    source_path: Path | None = None

    @property
    def kind(self) -> BenchmarkKind:
        """Return the effective execution kind for the case."""

        return BenchmarkKind.REPO if self.repo_target is not None else BenchmarkKind.PROMPT

    @classmethod
    def from_dict(cls, data: dict[str, object], *, source_path: Path | None = None) -> "BenchmarkCase":
        """Build and validate a benchmark case from JSON data."""

        required = ("schema_version", "id", "title", "mode", "prompt", "expectations")
        missing = [key for key in required if key not in data]
        if missing:
            raise ValueError(f"Case is missing required keys: {', '.join(missing)}")

        repo_target_raw = _optional_dict(data.get("repo"), "repo")

        return cls(
            schema_version=int(data["schema_version"]),
            id=str(data["id"]),
            title=str(data["title"]),
            mode=BenchmarkMode(str(data["mode"])),
            prompt=str(data["prompt"]),
            expectations=ExpectationSet.from_dict(_dict_value(data.get("expectations"), "expectations")),
            context=_string_list(data.get("context", []), "context"),
            context_files=_string_list(data.get("context_files", []), "context_files"),
            tags=_string_list(data.get("tags", []), "tags"),
            repo_target=(
                RepoTarget.from_dict(repo_target_raw, field_name="repo")
                if repo_target_raw is not None
                else None
            ),
            execution_policy_name=_optional_string(
                data.get("execution_policy"),
                "execution_policy",
            ),
            rule_policy_name=_optional_string(
                data.get("rule_policy"),
                "rule_policy",
            ),
            judge_policy_name=_optional_string(
                data.get("judge_policy"),
                "judge_policy",
            ),
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

        if self.repo_target is None:
            return None
        if self.source_path is None:
            raise ValueError("Cannot resolve repo paths without source_path.")
        return self.repo_target.resolve_root(self.source_path.parent)

    def resolve_working_dir(self) -> Path | None:
        """Resolve the effective working directory for repo-aware cases."""

        if self.repo_target is None:
            return None
        if self.source_path is None:
            raise ValueError("Cannot resolve repo paths without source_path.")
        return self.repo_target.resolve_working_dir_path(self.source_path.parent)


@dataclass(slots=True)
class BenchmarkSuite:
    """Suite-level defaults shared by many benchmark cases."""

    schema_version: int
    suite_id: str
    title: str
    default_skills: list[str] = field(default_factory=list)
    default_execution_policy: str = "isolated_prompt"
    default_rule_policy: str | None = None
    default_judge_policy: str | None = None
    rule_policies: dict[str, RuleEvaluationPolicy] = field(default_factory=dict)
    judge_policies: dict[str, JudgePolicy] = field(default_factory=dict)
    prompt_contract: PromptContract | None = None
    source_path: Path | None = None

    @classmethod
    def from_dict(cls, data: dict[str, object], *, source_path: Path | None = None) -> "BenchmarkSuite":
        """Build and validate a benchmark suite manifest."""

        required = ("schema_version", "suite_id", "title", "default_execution_policy")
        missing = [key for key in required if key not in data]
        if missing:
            raise ValueError(f"Suite manifest is missing required keys: {', '.join(missing)}")

        return cls(
            schema_version=int(data["schema_version"]),
            suite_id=str(data["suite_id"]),
            title=str(data["title"]),
            default_skills=_string_list(data.get("default_skills", []), "default_skills"),
            default_execution_policy=str(data["default_execution_policy"]),
            default_rule_policy=_optional_string(
                data.get("default_rule_policy"),
                "default_rule_policy",
            ),
            default_judge_policy=_optional_string(
                data.get("default_judge_policy"),
                "default_judge_policy",
            ),
            rule_policies=_rule_policies(
                _optional_dict(data.get("rule_policies"), "rule_policies") or {}
            ),
            judge_policies=_judge_policies(
                _optional_dict(data.get("judge_policies"), "judge_policies") or {}
            ),
            prompt_contract=PromptContract.from_dict(
                _optional_dict(data.get("prompt_contract"), "prompt_contract")
            ),
            source_path=source_path,
        )

    def resolve_default_skills(self) -> list[Path]:
        """Resolve suite-default skill paths relative to the suite manifest."""

        if self.source_path is None:
            raise ValueError("Cannot resolve suite skills without source_path.")
        base_dir = self.source_path.parent
        return [_resolve_path(base_dir, relative_path) for relative_path in self.default_skills]

    def resolve_rule_policy(self, name: str | None) -> RuleEvaluationPolicy | None:
        """Resolve a rule policy from suite-local definitions."""

        if name is None:
            return None
        try:
            return self.rule_policies[name]
        except KeyError as exc:
            available = ", ".join(sorted(self.rule_policies)) or "<none>"
            raise ValueError(
                f"Unknown rule policy {name!r} for suite {self.suite_id!r}. Available: {available}"
            ) from exc

    def resolve_judge_policy(self, name: str | None) -> JudgePolicy | None:
        """Resolve a judge policy from suite-local definitions."""

        if name is None:
            return None
        try:
            return self.judge_policies[name]
        except KeyError as exc:
            available = ", ".join(sorted(self.judge_policies)) or "<none>"
            raise ValueError(
                f"Unknown judge policy {name!r} for suite {self.suite_id!r}. Available: {available}"
            ) from exc


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


def _optional_int(
    value: object,
    field_name: str,
    *,
    default: int,
    minimum: int | None = None,
    maximum: int | None = None,
) -> int:
    """Validate optional integer fields."""

    if value is None:
        return default
    if not isinstance(value, int) or isinstance(value, bool):
        raise ValueError(f"Field {field_name!r} must be an integer when present.")
    if minimum is not None and value < minimum:
        raise ValueError(f"Field {field_name!r} must be >= {minimum}.")
    if maximum is not None and value > maximum:
        raise ValueError(f"Field {field_name!r} must be <= {maximum}.")
    return value


def _list_of_dicts(value: object, field_name: str) -> list[dict[str, object]]:
    """Validate list[object] where every element is a JSON object."""

    if not isinstance(value, list):
        raise ValueError(f"Field {field_name!r} must be a list.")
    items: list[dict[str, object]] = []
    for index, item in enumerate(value):
        items.append(_dict_value(item, f"{field_name}[{index}]"))
    return items


def _rule_policies(value: dict[str, object]) -> dict[str, RuleEvaluationPolicy]:
    """Parse suite-local rule policy definitions."""

    policies: dict[str, RuleEvaluationPolicy] = {}
    for name, payload in value.items():
        policies[str(name)] = RuleEvaluationPolicy.from_dict(
            str(name),
            _dict_value(payload, f"rule_policies.{name}"),
            field_name=f"rule_policies.{name}",
        )
    return policies


def _judge_policies(value: dict[str, object]) -> dict[str, JudgePolicy]:
    """Parse suite-local judge policy definitions."""

    policies: dict[str, JudgePolicy] = {}
    for name, payload in value.items():
        policies[str(name)] = JudgePolicy.from_dict(
            str(name),
            _dict_value(payload, f"judge_policies.{name}"),
            field_name=f"judge_policies.{name}",
        )
    return policies


def _resolve_path(base_dir: Path, path_value: str) -> Path:
    """Resolve an absolute or base-relative path."""

    path = Path(path_value)
    if not path.is_absolute():
        path = base_dir / path
    return path.resolve()
