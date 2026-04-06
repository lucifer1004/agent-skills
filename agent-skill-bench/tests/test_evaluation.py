"""Deterministic rule assessment tests."""

from agent_skill_bench import (
    BenchmarkCase,
    BenchmarkMode,
    BenchmarkSuite,
    PromptContract,
    ResolvedCase,
    RuleEvaluationPolicy,
    evaluate_rule_assessment,
    get_execution_policy,
)


def _suite_with_generate_policy() -> BenchmarkSuite:
    return BenchmarkSuite(
        schema_version=1,
        suite_id="uiux",
        title="UIUX",
        default_execution_policy="isolated_prompt",
        default_rule_policy="uiux-default",
        rule_policies={
            "uiux-default": BenchmarkSuite.from_dict(
                {
                    "schema_version": 1,
                    "suite_id": "uiux",
                    "title": "UIUX",
                    "default_execution_policy": "isolated_prompt",
                    "rule_policies": {
                        "uiux-default": {
                            "forbid_code_fences": True,
                            "require_first_heading": True,
                            "mode_rules": {
                                "Generate": [
                                    {
                                        "code": "states_have_terms",
                                        "kind": "section_matches_regex",
                                        "section": "Required States",
                                        "pattern": "\\b(loading|error|disabled)\\b",
                                        "message": "Required States names concrete states.",
                                    },
                                    {
                                        "code": "risks_present",
                                        "kind": "section_non_empty",
                                        "section": "Risks",
                                        "message": "Risks section is non-empty.",
                                    },
                                ]
                            },
                        }
                    },
                }
            ).rule_policies["uiux-default"]
        },
        prompt_contract=PromptContract(
            mode_headings={
                BenchmarkMode.GENERATE: [
                    "Screen Goal",
                    "Primary User Task",
                    "Information Priority",
                    "Layout Blocks",
                    "Key Components",
                    "Required States",
                    "Visual Rules",
                    "Risks",
                ]
            }
        ),
    )


def test_rule_assessment_uses_suite_owned_rules():
    case = ResolvedCase(
        suite=_suite_with_generate_policy(),
        case=BenchmarkCase(
            schema_version=1,
            id="uiux.generate.sample",
            title="Sample",
            mode=BenchmarkMode.GENERATE,
            prompt="Design a page.",
        ),
        execution_policy=get_execution_policy("isolated_prompt"),
        rule_policy=_suite_with_generate_policy().rule_policies["uiux-default"],
    )

    output = """## Screen Goal
Choose a plan quickly.

## Primary User Task
Compare plans and commit.

## Information Priority
Price, differences, and CTA.

## Layout Blocks
Hero, plan grid, FAQ.

## Key Components
Plan cards, toggle, FAQ.

## Required States
Loading, error, and disabled CTA.

## Visual Rules
Clarity before ornament.

## Risks
Too many comparison points can slow scanning.
"""

    assessment = evaluate_rule_assessment(case, output)

    assert assessment.passed is True
    assert assessment.failure_modes == []
    assert all(check.passed for check in assessment.contract_checks)
    assert all(check.passed for check in assessment.rule_checks)


def test_rule_assessment_fails_when_policy_conditions_fail():
    suite = _suite_with_generate_policy()
    case = ResolvedCase(
        suite=suite,
        case=BenchmarkCase(
            schema_version=1,
            id="uiux.generate.sample",
            title="Sample",
            mode=BenchmarkMode.GENERATE,
            prompt="Design a page.",
        ),
        execution_policy=get_execution_policy("isolated_prompt"),
        rule_policy=suite.rule_policies["uiux-default"],
    )

    output = """Preface

## Screen Goal
Choose a plan quickly.

## Primary User Task
Compare plans and commit.

## Information Priority
Price, differences, and CTA.

## Layout Blocks
Hero, plan grid, FAQ.

## Key Components
Plan cards, toggle, FAQ.

## Required States
Keep it polished.

## Visual Rules
Clarity before ornament.

## Risks

```html
<div>bad</div>
```
"""

    assessment = evaluate_rule_assessment(case, output)

    assert assessment.passed is False
    assert "starts_with_required_heading" in assessment.failure_modes
    assert "no_code_fences" in assessment.failure_modes
    assert "states_have_terms" in assessment.failure_modes


def test_rule_assessment_treats_nested_subheadings_as_parent_section_content():
    suite = BenchmarkSuite(
        schema_version=1,
        suite_id="uiux",
        title="UIUX",
        default_execution_policy="isolated_prompt",
        default_rule_policy="uiux-handoff",
        rule_policies={
            "uiux-handoff": RuleEvaluationPolicy(
                name="uiux-handoff",
                forbid_code_fences=True,
                require_first_heading=True,
            )
        },
        prompt_contract=PromptContract(
            mode_headings={
                BenchmarkMode.IMPLEMENT_HANDOFF: [
                    "Scope",
                    "Component Requirements",
                    "State Matrix",
                    "Layout Rules",
                ]
            }
        ),
    )
    case = ResolvedCase(
        suite=suite,
        case=BenchmarkCase(
            schema_version=1,
            id="uiux.handoff.nested-headings",
            title="Nested Headings",
            mode=BenchmarkMode.IMPLEMENT_HANDOFF,
            prompt="Produce a handoff.",
        ),
        execution_policy=get_execution_policy("isolated_prompt"),
        rule_policy=suite.rule_policies["uiux-handoff"],
    )

    output = """## Scope
Summary layer only.

## Component Requirements
### Metric Card
- Variant A
- Variant B

## State Matrix
### Loading
- Skeleton

## Layout Rules
### Desktop
- Three columns
"""

    assessment = evaluate_rule_assessment(case, output)

    assert assessment.passed is True
    assert "required_sections_non_empty" not in assessment.failure_modes


def test_rule_assessment_allows_optional_h1_title_block_before_required_sections():
    suite = BenchmarkSuite(
        schema_version=1,
        suite_id="uiux",
        title="UIUX",
        default_execution_policy="isolated_prompt",
        default_rule_policy="uiux-generate",
        rule_policies={
            "uiux-generate": RuleEvaluationPolicy(
                name="uiux-generate",
                forbid_code_fences=True,
                require_first_heading=True,
            )
        },
        prompt_contract=PromptContract(
            required_heading_level=2,
            allow_document_title=True,
            mode_headings={
                BenchmarkMode.GENERATE: [
                    "Screen Goal",
                    "Layout Blocks",
                ]
            },
        ),
    )
    case = ResolvedCase(
        suite=suite,
        case=BenchmarkCase(
            schema_version=1,
            id="uiux.generate.h1-title",
            title="H1 Title",
            mode=BenchmarkMode.GENERATE,
            prompt="Produce a generate answer.",
        ),
        execution_policy=get_execution_policy("isolated_prompt"),
        rule_policy=suite.rule_policies["uiux-generate"],
    )

    output = """# Pricing Page Spec

---

## Screen Goal
Help buyers choose a plan quickly.

## Layout Blocks
Hero, comparison grid, FAQ.
"""

    assessment = evaluate_rule_assessment(case, output)

    assert assessment.passed is True
    assert "starts_with_required_heading" not in assessment.failure_modes


def test_rule_assessment_rejects_h1_with_body_before_first_required_section():
    suite = BenchmarkSuite(
        schema_version=1,
        suite_id="uiux",
        title="UIUX",
        default_execution_policy="isolated_prompt",
        default_rule_policy="uiux-generate",
        rule_policies={
            "uiux-generate": RuleEvaluationPolicy(
                name="uiux-generate",
                forbid_code_fences=True,
                require_first_heading=True,
            )
        },
        prompt_contract=PromptContract(
            required_heading_level=2,
            allow_document_title=True,
            mode_headings={
                BenchmarkMode.GENERATE: [
                    "Screen Goal",
                    "Layout Blocks",
                ]
            },
        ),
    )
    case = ResolvedCase(
        suite=suite,
        case=BenchmarkCase(
            schema_version=1,
            id="uiux.generate.h1-body",
            title="H1 Body",
            mode=BenchmarkMode.GENERATE,
            prompt="Produce a generate answer.",
        ),
        execution_policy=get_execution_policy("isolated_prompt"),
        rule_policy=suite.rule_policies["uiux-generate"],
    )

    output = """# Pricing Page Spec

This intro paragraph should not appear before the required sections.

## Screen Goal
Help buyers choose a plan quickly.

## Layout Blocks
Hero, comparison grid, FAQ.
"""

    assessment = evaluate_rule_assessment(case, output)

    assert assessment.passed is False
    assert "starts_with_required_heading" in assessment.failure_modes
