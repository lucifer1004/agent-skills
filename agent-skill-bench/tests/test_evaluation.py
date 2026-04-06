"""Evaluation engine tests."""

from agent_skill_bench import (
    BenchmarkCase,
    BenchmarkMode,
    BenchmarkPromptContract,
    BenchmarkSuite,
    BenchmarkRunner,
    ResolvedBenchmarkCase,
    evaluate_output,
    get_execution_profile,
)


def _suite_with_generate_profile() -> BenchmarkSuite:
    return BenchmarkSuite(
        schema_version=1,
        suite_id="uiux",
        title="UIUX",
        default_execution_profile="isolated_prompt",
        default_evaluation_profile="uiux-default",
        evaluation_profiles={
            "uiux-default": BenchmarkSuite.from_dict(
                {
                    "schema_version": 1,
                    "suite_id": "uiux",
                    "title": "UIUX",
                    "default_execution_profile": "isolated_prompt",
                    "evaluation_profiles": {
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
            ).evaluation_profiles["uiux-default"]
        },
        benchmark_prompt=BenchmarkPromptContract(
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


def test_evaluate_output_uses_suite_owned_rules():
    case = ResolvedBenchmarkCase(
        suite=_suite_with_generate_profile(),
        case=BenchmarkCase(
            schema_version=1,
            id="uiux.generate.sample",
            title="Sample",
            mode=BenchmarkMode.GENERATE,
            prompt="Design a page.",
        ),
        execution_profile=get_execution_profile("isolated_prompt"),
        evaluation_profile="uiux-default",
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

    evaluation = evaluate_output(case, output)

    assert evaluation.passed is True
    assert evaluation.failure_modes == []
    assert all(check.passed for check in evaluation.contract_checks)
    assert all(check.passed for check in evaluation.rule_checks)


def test_evaluate_output_fails_when_rule_profile_conditions_fail():
    case = ResolvedBenchmarkCase(
        suite=_suite_with_generate_profile(),
        case=BenchmarkCase(
            schema_version=1,
            id="uiux.generate.sample",
            title="Sample",
            mode=BenchmarkMode.GENERATE,
            prompt="Design a page.",
        ),
        execution_profile=get_execution_profile("isolated_prompt"),
        evaluation_profile="uiux-default",
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

    evaluation = evaluate_output(case, output)

    assert evaluation.passed is False
    assert "starts_with_required_heading" in evaluation.failure_modes
    assert "no_code_fences" in evaluation.failure_modes
    assert "states_have_terms" in evaluation.failure_modes
