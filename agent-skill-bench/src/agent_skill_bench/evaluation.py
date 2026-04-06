"""Generic rule-based evaluation for benchmark run outputs."""

from __future__ import annotations

from dataclasses import dataclass, field
import re

from .fixtures import (
    BenchmarkEvaluationProfile,
    BenchmarkEvaluationRule,
    EvaluationRuleKind,
    ResolvedBenchmarkCase,
)

_HEADING_RE = re.compile(r"^\s{0,3}#{1,6}\s+(?P<title>.+?)\s*$", re.MULTILINE)
_CODE_FENCE_RE = re.compile(r"```")


@dataclass(slots=True)
class EvaluationCheck:
    """One machine-checkable evaluation result."""

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
class BenchmarkEvaluation:
    """Rule-based evaluation artifact for one run result."""

    profile: str | None
    passed: bool
    contract_checks: list[EvaluationCheck] = field(default_factory=list)
    rule_checks: list[EvaluationCheck] = field(default_factory=list)
    failure_modes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, object]:
        """Convert evaluation into JSON-serializable data."""

        return {
            "profile": self.profile,
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
class _ParsedOutput:
    """Structured view of a benchmark answer."""

    headings: list[str]
    sections: dict[str, str]
    preamble: str


def evaluate_output(case: ResolvedBenchmarkCase, output_text: str) -> BenchmarkEvaluation:
    """Evaluate a benchmark output with deterministic suite-owned rules."""

    parsed = _parse_output(output_text)
    profile = case.suite.resolve_evaluation_profile(case.evaluation_profile)
    contract_checks = _build_contract_checks(case, output_text, parsed, profile)
    rule_checks = _build_profile_checks(case, output_text, parsed, profile)
    all_checks = contract_checks + rule_checks

    return BenchmarkEvaluation(
        profile=case.evaluation_profile,
        passed=all(check.passed for check in all_checks),
        contract_checks=contract_checks,
        rule_checks=rule_checks,
        failure_modes=[check.code for check in all_checks if not check.passed],
    )


def _build_contract_checks(
    case: ResolvedBenchmarkCase,
    output_text: str,
    parsed: _ParsedOutput,
    profile: BenchmarkEvaluationProfile | None,
) -> list[EvaluationCheck]:
    """Build generic suite-contract checks shared by all domains."""

    checks = [
        EvaluationCheck(
            code="non_empty_output",
            passed=bool(output_text.strip()),
            message="Output must not be empty.",
        )
    ]

    required_headings = []
    if case.suite.benchmark_prompt is not None:
        required_headings = case.suite.benchmark_prompt.mode_headings.get(case.mode, [])

    if required_headings:
        missing = [heading for heading in required_headings if heading not in parsed.sections]
        duplicates = [heading for heading in required_headings if parsed.headings.count(heading) > 1]
        observed_required = [heading for heading in parsed.headings if heading in required_headings]
        empty_sections = [
            heading for heading in required_headings if not parsed.sections.get(heading, "").strip()
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

        require_first_heading = profile.require_first_heading if profile is not None else False
        if require_first_heading:
            starts_cleanly = not parsed.preamble.strip() and (
                not parsed.headings or parsed.headings[0] == required_headings[0]
            )
            checks.append(
                EvaluationCheck(
                    code="starts_with_required_heading",
                    passed=starts_cleanly,
                    message=(
                        "Answer starts directly with the first required heading."
                        if starts_cleanly
                        else "Answer does not start with the first required heading."
                    ),
                )
            )

    forbid_code_fences = profile.forbid_code_fences if profile is not None else False
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


def _build_profile_checks(
    case: ResolvedBenchmarkCase,
    output_text: str,
    parsed: _ParsedOutput,
    profile: BenchmarkEvaluationProfile | None,
) -> list[EvaluationCheck]:
    """Build suite-owned declarative rule checks."""

    if profile is None:
        return []

    checks: list[EvaluationCheck] = []
    for rule in profile.mode_rules.get(case.mode, []):
        checks.append(_evaluate_rule(rule, output_text=output_text, parsed=parsed))
    return checks


def _evaluate_rule(
    rule: BenchmarkEvaluationRule,
    *,
    output_text: str,
    parsed: _ParsedOutput,
) -> EvaluationCheck:
    """Evaluate one declarative rule against the output."""

    if rule.kind == EvaluationRuleKind.SECTION_NON_EMPTY:
        section_text = parsed.sections.get(rule.section or "", "")
        passed = bool(section_text.strip())
    elif rule.kind == EvaluationRuleKind.SECTION_MATCHES_REGEX:
        section_text = parsed.sections.get(rule.section or "", "")
        passed = re.search(rule.pattern or "", section_text, re.IGNORECASE) is not None
    elif rule.kind == EvaluationRuleKind.SECTION_CONTAINS_LIST_ITEM:
        section_text = parsed.sections.get(rule.section or "", "")
        passed = any(line.lstrip().startswith(("-", "*")) for line in section_text.splitlines())
    elif rule.kind == EvaluationRuleKind.OUTPUT_NOT_MATCHES_REGEX:
        passed = re.search(rule.pattern or "", output_text, re.IGNORECASE) is None
    else:
        raise ValueError(f"Unsupported evaluation rule kind: {rule.kind}")

    return EvaluationCheck(
        code=rule.code,
        passed=passed,
        message=rule.message,
    )


def _parse_output(output_text: str) -> _ParsedOutput:
    """Parse markdown headings and section bodies from one output."""

    matches = list(_HEADING_RE.finditer(output_text))
    headings = [match.group("title").strip() for match in matches]
    sections: dict[str, str] = {}

    preamble = output_text[: matches[0].start()] if matches else output_text
    for index, match in enumerate(matches):
        title = match.group("title").strip()
        body_start = match.end()
        body_end = matches[index + 1].start() if index + 1 < len(matches) else len(output_text)
        sections[title] = output_text[body_start:body_end].strip()

    return _ParsedOutput(
        headings=headings,
        sections=sections,
        preamble=preamble.strip(),
    )
