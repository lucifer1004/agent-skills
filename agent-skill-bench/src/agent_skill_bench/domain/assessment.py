"""Assessment entities and deterministic rule evaluation."""

from __future__ import annotations

from dataclasses import dataclass, field
from markdown_it import MarkdownIt
import re
from typing import TYPE_CHECKING

from .catalog import EvaluationRule, EvaluationRuleKind, JudgeDimension, JudgePolicy

if TYPE_CHECKING:
    from .execution import ResolvedCase

_CODE_FENCE_RE = re.compile(r"```")
_MARKDOWN = MarkdownIt("commonmark")


@dataclass(slots=True)
class EvaluationCheck:
    """One machine-checkable assessment result."""

    code: str
    passed: bool
    message: str

    def to_dict(self) -> dict[str, object]:
        """Convert one check into JSON-serializable data."""

        return {
            "code": self.code,
            "passed": self.passed,
            "message": self.message,
        }


@dataclass(slots=True)
class RuleAssessment:
    """Deterministic assessment artifact for one run result."""

    policy: str | None
    passed: bool
    contract_checks: list[EvaluationCheck] = field(default_factory=list)
    rule_checks: list[EvaluationCheck] = field(default_factory=list)
    failure_modes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, object]:
        """Convert the assessment into JSON-serializable data."""

        return {
            "policy": self.policy,
            "passed": self.passed,
            "summary": {
                "contract_passed": sum(1 for check in self.contract_checks if check.passed),
                "contract_failed": sum(1 for check in self.contract_checks if not check.passed),
                "rules_passed": sum(1 for check in self.rule_checks if check.passed),
                "rules_failed": sum(1 for check in self.rule_checks if not check.passed),
            },
            "contract_checks": [check.to_dict() for check in self.contract_checks],
            "rule_checks": [check.to_dict() for check in self.rule_checks],
            "failure_modes": list(self.failure_modes),
        }


@dataclass(slots=True)
class DimensionScore:
    """One judge-scored dimension."""

    name: str
    score: int
    rationale: str

    def to_dict(self) -> dict[str, object]:
        """Convert one dimension score into JSON-serializable data."""

        return {
            "name": self.name,
            "score": self.score,
            "rationale": self.rationale,
        }


@dataclass(slots=True)
class JudgeAssessment:
    """Normalized judge result for one benchmark run."""

    judge_runtime_name: str
    passed: bool
    summary: str
    dimensions: list[DimensionScore] = field(default_factory=list)
    metadata: dict[str, str | int | float | bool] = field(default_factory=dict)

    def to_dict(self) -> dict[str, object]:
        """Convert a judge result into JSON-serializable data."""

        return {
            "judge_runtime_name": self.judge_runtime_name,
            "passed": self.passed,
            "summary": self.summary,
            "dimensions": [dimension.to_dict() for dimension in self.dimensions],
            "metadata": dict(self.metadata),
        }


@dataclass(slots=True)
class JudgeTask:
    """Standardized judge task assembled by the application layer."""

    case: "ResolvedCase"
    candidate_output: str
    rule_assessment: RuleAssessment | None
    judge_policy: JudgePolicy


@dataclass(slots=True)
class _ParsedOutput:
    """Structured view of a benchmark answer."""

    heading_nodes: list["_HeadingNode"]
    sections: dict[tuple[int, str], str]
    preamble: str
    lines: list[str]


@dataclass(slots=True)
class _HeadingNode:
    """One parsed markdown heading with its section boundaries."""

    title: str
    level: int
    start_line: int
    body_start_line: int
    body_end_line: int


def evaluate_rule_assessment(case: "ResolvedCase", output_text: str) -> RuleAssessment:
    """Evaluate a benchmark output with deterministic suite-owned rules."""

    parsed = _parse_output(output_text)
    policy = case.rule_policy
    contract_checks = _build_contract_checks(case, output_text, parsed)
    rule_checks = _build_policy_checks(case, output_text, parsed)
    all_checks = contract_checks + rule_checks

    return RuleAssessment(
        policy=policy.name if policy is not None else None,
        passed=all(check.passed for check in all_checks),
        contract_checks=contract_checks,
        rule_checks=rule_checks,
        failure_modes=[check.code for check in all_checks if not check.passed],
    )


def default_judge_policy() -> JudgePolicy:
    """Return a generic fallback judge policy when suites define none."""

    return JudgePolicy(
        name="default",
        preamble=[
            "You are judging one benchmark output for an agent skill.",
            "Use the benchmark task, expectations, required headings, and the candidate answer below.",
        ],
        shared_rules=["Be strict about contract adherence and avoid rewarding generic filler."],
        dimensions=[
            JudgeDimension(
                name="task_fit",
                description="Does the answer perform the requested task rather than drifting into meta commentary or the wrong mode?",
            ),
            JudgeDimension(
                name="contract_adherence",
                description="Does the answer follow the required structure, headings, and explicit benchmark output contract?",
            ),
            JudgeDimension(
                name="expectation_coverage",
                description="Does the answer cover the must-cover expectations and avoid obvious must-avoid failures?",
            ),
            JudgeDimension(
                name="actionability",
                description="Is the answer concrete enough that a downstream user could act on it without major reinterpretation?",
            ),
        ],
        pass_guidance="Set passed=true only if the output is broadly benchmark-worthy, not merely acceptable.",
        include_rule_assessment=True,
    )


def _build_contract_checks(
    case: "ResolvedCase",
    output_text: str,
    parsed: _ParsedOutput,
) -> list[EvaluationCheck]:
    """Build generic suite-contract checks shared by all domains."""

    checks = [
        EvaluationCheck(
            code="non_empty_output",
            passed=bool(output_text.strip()),
            message="Output must not be empty.",
        )
    ]

    required_headings: list[str] = []
    if case.suite.prompt_contract is not None:
        required_headings = case.suite.prompt_contract.mode_headings.get(case.mode, [])

    if required_headings:
        required_level = _required_heading_level(case)
        missing = [heading for heading in required_headings if (required_level, heading) not in parsed.sections]
        duplicates = [
            heading
            for heading in required_headings
            if sum(
                1
                for node in parsed.heading_nodes
                if node.level == required_level and node.title == heading
            )
            > 1
        ]
        observed_required = [
            node.title
            for node in parsed.heading_nodes
            if node.level == required_level and node.title in required_headings
        ]
        empty_sections = [
            heading
            for heading in required_headings
            if not parsed.sections.get((required_level, heading), "").strip()
        ]

        checks.extend(
            [
                EvaluationCheck(
                    code="required_headings_present",
                    passed=not missing,
                    message=(
                        "All required headings are present."
                        if not missing
                        else f"Missing required headings: {', '.join(missing)}."
                    ),
                ),
                EvaluationCheck(
                    code="required_headings_unique",
                    passed=not duplicates,
                    message=(
                        "Each required heading appears exactly once."
                        if not duplicates
                        else f"Repeated required headings: {', '.join(sorted(set(duplicates)))}."
                    ),
                ),
                EvaluationCheck(
                    code="required_headings_in_order",
                    passed=observed_required == required_headings,
                    message=(
                        "Required headings appear exactly once and in order."
                        if observed_required == required_headings
                        else f"Observed required-heading order: {observed_required!r}."
                    ),
                ),
                EvaluationCheck(
                    code="required_sections_non_empty",
                    passed=not empty_sections,
                    message=(
                        "All required sections have content."
                        if not empty_sections
                        else f"Empty required sections: {', '.join(empty_sections)}."
                    ),
                ),
            ]
        )

        require_first_heading = case.rule_policy.require_first_heading if case.rule_policy else False
        if require_first_heading:
            starts_cleanly = _starts_with_required_heading(
                parsed,
                first_required_heading=required_headings[0],
                required_level=required_level,
                allow_document_title=_allow_document_title(case),
            )
            checks.append(
                EvaluationCheck(
                    code="starts_with_required_heading",
                    passed=starts_cleanly,
                    message=(
                        "Answer starts with an optional title block followed by the first required section."
                        if starts_cleanly
                        else "Answer must start with either an optional title block or the first required section."
                    ),
                )
            )

    forbid_code_fences = case.rule_policy.forbid_code_fences if case.rule_policy else False
    if forbid_code_fences:
        has_code_fence = _CODE_FENCE_RE.search(output_text) is not None
        checks.append(
            EvaluationCheck(
                code="no_code_fences",
                passed=not has_code_fence,
                message=(
                    "Answer does not include fenced code blocks."
                    if not has_code_fence
                    else "Answer includes fenced code blocks."
                ),
            )
        )

    return checks


def _build_policy_checks(
    case: "ResolvedCase",
    output_text: str,
    parsed: _ParsedOutput,
) -> list[EvaluationCheck]:
    """Build suite-owned declarative rule checks."""

    if case.rule_policy is None:
        return []

    checks: list[EvaluationCheck] = []
    section_level = _required_heading_level(case)
    for rule in case.rule_policy.mode_rules.get(case.mode, []):
        checks.append(
            _evaluate_rule(
                rule,
                output_text=output_text,
                parsed=parsed,
                section_level=section_level,
            )
        )
    return checks


def _evaluate_rule(
    rule: EvaluationRule,
    *,
    output_text: str,
    parsed: _ParsedOutput,
    section_level: int,
) -> EvaluationCheck:
    """Evaluate one declarative rule against the output."""

    if rule.kind == EvaluationRuleKind.SECTION_NON_EMPTY:
        section_text = _section_text(parsed, rule.section or "", preferred_level=section_level)
        passed = bool(section_text.strip())
    elif rule.kind == EvaluationRuleKind.SECTION_MATCHES_REGEX:
        section_text = _section_text(parsed, rule.section or "", preferred_level=section_level)
        passed = re.search(rule.pattern or "", section_text, re.IGNORECASE) is not None
    elif rule.kind == EvaluationRuleKind.SECTION_CONTAINS_LIST_ITEM:
        section_text = _section_text(parsed, rule.section or "", preferred_level=section_level)
        passed = any(line.lstrip().startswith(("-", "*")) for line in section_text.splitlines())
    elif rule.kind == EvaluationRuleKind.OUTPUT_NOT_MATCHES_REGEX:
        passed = re.search(rule.pattern or "", output_text, re.IGNORECASE) is None
    else:
        raise ValueError(f"Unsupported evaluation rule kind: {rule.kind}")

    return EvaluationCheck(code=rule.code, passed=passed, message=rule.message)


def _parse_output(output_text: str) -> _ParsedOutput:
    """Parse markdown headings and section bodies from one output."""

    lines = output_text.splitlines(keepends=True)
    heading_nodes = _collect_heading_nodes(output_text, line_count=len(lines))
    sections = {
        (heading.level, heading.title): _slice_lines(
            lines, heading.body_start_line, heading.body_end_line
        ).strip()
        for heading in heading_nodes
    }
    preamble_end_line = heading_nodes[0].start_line if heading_nodes else len(lines)
    preamble = _slice_lines(lines, 0, preamble_end_line).strip()
    return _ParsedOutput(
        heading_nodes=heading_nodes,
        sections=sections,
        preamble=preamble,
        lines=lines,
    )


def _collect_heading_nodes(output_text: str, *, line_count: int) -> list[_HeadingNode]:
    """Build heading nodes with section boundaries from the markdown token stream."""

    tokens = _MARKDOWN.parse(output_text)
    raw_headings: list[tuple[str, int, int, int]] = []

    index = 0
    while index < len(tokens):
        token = tokens[index]
        if token.type != "heading_open" or token.map is None:
            index += 1
            continue

        inline_index = index + 1
        if inline_index >= len(tokens) or tokens[inline_index].type != "inline":
            index += 1
            continue

        title = tokens[inline_index].content.strip()
        level = int(token.tag[1:])
        start_line, body_start_line = token.map
        raw_headings.append((title, level, start_line, body_start_line))
        index += 3

    nodes: list[_HeadingNode] = []
    for index, (title, level, start_line, body_start_line) in enumerate(raw_headings):
        body_end_line = line_count
        for next_title, next_level, next_start_line, _ in raw_headings[index + 1 :]:
            del next_title
            if next_level <= level:
                body_end_line = next_start_line
                break
        nodes.append(
            _HeadingNode(
                title=title,
                level=level,
                start_line=start_line,
                body_start_line=body_start_line,
                body_end_line=body_end_line,
            )
        )
    return nodes


def _slice_lines(lines: list[str], start_line: int, end_line: int) -> str:
    """Return the text slice between two 0-based line offsets."""

    return "".join(lines[start_line:end_line])


def _required_heading_level(case: "ResolvedCase") -> int:
    """Return the contract heading level used for required sections."""

    contract = case.suite.prompt_contract
    if contract is None:
        return 2
    return contract.required_heading_level


def _allow_document_title(case: "ResolvedCase") -> bool:
    """Return whether the contract allows a single document title before sections."""

    contract = case.suite.prompt_contract
    if contract is None:
        return False
    return contract.allow_document_title


def _section_text(parsed: _ParsedOutput, title: str, *, preferred_level: int) -> str:
    """Return section text, preferring the contract heading level."""

    exact_match = parsed.sections.get((preferred_level, title))
    if exact_match is not None:
        return exact_match

    for node in parsed.heading_nodes:
        if node.title == title:
            return parsed.sections.get((node.level, node.title), "")
    return ""


def _starts_with_required_heading(
    parsed: _ParsedOutput,
    *,
    first_required_heading: str,
    required_level: int,
    allow_document_title: bool,
) -> bool:
    """Return whether the output starts with the required section structure."""

    first_required_index = next(
        (
            index
            for index, node in enumerate(parsed.heading_nodes)
            if node.level == required_level and node.title == first_required_heading
        ),
        None,
    )
    if first_required_index is None:
        return False

    first_required_node = parsed.heading_nodes[first_required_index]
    if not allow_document_title:
        return not _slice_lines(parsed.lines, 0, first_required_node.start_line).strip()

    preceding_nodes = parsed.heading_nodes[:first_required_index]
    if not preceding_nodes:
        return not _slice_lines(parsed.lines, 0, first_required_node.start_line).strip()
    if len(preceding_nodes) != 1 or preceding_nodes[0].level != 1:
        return False

    title_node = preceding_nodes[0]
    if _slice_lines(parsed.lines, 0, title_node.start_line).strip():
        return False
    between_title_and_required = _slice_lines(
        parsed.lines,
        title_node.body_start_line,
        first_required_node.start_line,
    )
    return _is_allowed_title_block_padding(between_title_and_required)


def _is_allowed_title_block_padding(text: str) -> bool:
    """Return whether the title block padding is limited to blank lines or thematic breaks."""

    allowed_thematic_breaks = {"---", "***", "___"}
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if stripped not in allowed_thematic_breaks:
            return False
    return True
