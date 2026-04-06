"""Codex CLI judge adapter."""

from __future__ import annotations

import json
from pathlib import Path
import subprocess
from tempfile import TemporaryDirectory

from agent_skill_bench.evaluation import BenchmarkEvaluation
from agent_skill_bench.fixtures import (
    BenchmarkJudgeDimension,
    BenchmarkJudgeProfile,
    ResolvedBenchmarkCase,
)

from .base import BenchmarkJudge, JudgeDimensionScore, JudgeEvaluation


class CodexCLIJudge(BenchmarkJudge):
    """Judge backed by the official Codex CLI."""

    name = "codex"

    def __init__(
        self,
        *,
        cli_path: str | None = None,
        timeout_seconds: float | None = None,
        model: str | None = None,
    ) -> None:
        self.cli_path = cli_path
        self.timeout_seconds = timeout_seconds
        self.model = model

    def evaluate_case(
        self,
        case: ResolvedBenchmarkCase,
        *,
        output_text: str,
        rule_evaluation: BenchmarkEvaluation | None = None,
    ) -> JudgeEvaluation:
        """Judge one benchmark output via Codex non-interactive exec."""

        with TemporaryDirectory(prefix="agent-skill-bench-judge-") as tmp_dir:
            tmp_path = Path(tmp_dir)
            schema_path = tmp_path / "judge-schema.json"
            output_path = tmp_path / "judge-output.json"
            profile_name = case.judge_profile or case.suite.default_judge_profile
            profile = case.suite.resolve_judge_profile(profile_name) or _default_judge_profile()
            schema_path.write_text(json.dumps(_judge_schema(profile), indent=2), encoding="utf-8")

            cmd = [
                self.cli_path or "codex",
                "exec",
                "--json",
                "--skip-git-repo-check",
                "--sandbox",
                "read-only",
                "--cd",
                str(tmp_path),
                "--output-schema",
                str(schema_path),
                "--output-last-message",
                str(output_path),
                "-",
            ]
            if self.model is not None:
                cmd.extend(["--model", self.model])

            completed = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=self.timeout_seconds,
                input=_judge_prompt(case, output_text, rule_evaluation, profile),
            )
            if completed.returncode != 0:
                raise RuntimeError(
                    f"Codex judge failed for case '{case.id}' with exit code "
                    f"{completed.returncode}. stdout:\n{completed.stdout.strip()}\n\nstderr:\n{completed.stderr.strip()}"
                )

            payload = json.loads(output_path.read_text(encoding="utf-8"))
            if not isinstance(payload, dict):
                raise RuntimeError(f"Codex judge returned non-object JSON for case '{case.id}'.")

            dimensions = []
            for item in payload.get("dimensions", []):
                if not isinstance(item, dict):
                    continue
                dimensions.append(
                    JudgeDimensionScore(
                        name=str(item.get("name", "")),
                        score=int(item.get("score", 0)),
                        rationale=str(item.get("rationale", "")),
                    )
                )

            metadata: dict[str, str | int | float | bool] = {
                "schema_enforced": True,
                "stderr_chars": len(completed.stderr or ""),
            }

            return JudgeEvaluation(
                judge_name=self.name,
                passed=bool(payload.get("passed")),
                summary=str(payload.get("summary", "")),
                dimensions=dimensions,
                metadata=metadata,
            )


def _judge_prompt(
    case: ResolvedBenchmarkCase,
    output_text: str,
    rule_evaluation: BenchmarkEvaluation | None,
    profile: BenchmarkJudgeProfile,
) -> str:
    """Build a suite-aware benchmark judge prompt."""

    required_headings: list[str] = []
    if case.suite.benchmark_prompt is not None:
        required_headings = case.suite.benchmark_prompt.mode_headings.get(case.mode, [])

    sections = list(profile.preamble) or [
        "You are judging one benchmark output for an agent skill.",
        "Use the benchmark task, expectations, required headings, and the candidate answer below.",
    ]
    sections.extend(
        [
            "",
            "Case:",
            f"- id: {case.id}",
            f"- suite_id: {case.suite_id}",
            f"- mode: {case.mode.value}",
            "",
            "User Request:",
            case.case.prompt,
        ]
    )
    if case.case.context:
        sections.extend(["", "Context Notes:"])
        sections.extend(f"- {item}" for item in case.case.context)
    if required_headings:
        sections.extend(["", "Required Headings:"])
        sections.extend(f"- {heading}" for heading in required_headings)

    expectations = case.case.expectations
    if expectations.must_cover:
        sections.extend(["", "Must Cover:"])
        sections.extend(f"- {item}" for item in expectations.must_cover)
    if expectations.must_avoid:
        sections.extend(["", "Must Avoid:"])
        sections.extend(f"- {item}" for item in expectations.must_avoid)
    if expectations.golden_signals:
        sections.extend(["", "Golden Signals:"])
        sections.extend(f"- {item}" for item in expectations.golden_signals)

    if profile.shared_rules:
        sections.extend(["", "Judge Rules:"])
        sections.extend(f"- {item}" for item in profile.shared_rules)

    if profile.include_rule_evaluation and rule_evaluation is not None:
        sections.extend(
            [
                "",
                "Existing Rule Evaluation Summary:",
                f"- passed: {rule_evaluation.passed}",
                f"- failure_modes: {', '.join(rule_evaluation.failure_modes) or '<none>'}",
            ]
        )

    sections.extend(
        [
            "",
            "Candidate Output:",
            output_text,
            "",
            "Score exactly these dimensions from 0 to 3:",
        ]
    )
    for dimension in profile.dimensions:
        sections.append(f"- {dimension.name}: {dimension.description}")
    sections.extend(
        [
            "",
            profile.pass_guidance
            or "Set passed=true only if the output is broadly benchmark-worthy, not merely acceptable.",
            "Return only JSON matching the provided schema.",
        ]
    )
    return "\n".join(sections)


def _judge_schema(profile: BenchmarkJudgeProfile) -> dict[str, object]:
    """Return the JSON schema for Codex judge responses."""

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
                            "enum": [dimension.name for dimension in profile.dimensions],
                        },
                        "score": {"type": "integer", "minimum": 0, "maximum": 3},
                        "rationale": {"type": "string"},
                    },
                },
            },
        },
    }


def _default_judge_profile() -> BenchmarkJudgeProfile:
    """Return a generic fallback judge profile when suites define none."""

    return BenchmarkJudgeProfile(
        name="default",
        preamble=[
            "You are judging one benchmark output for an agent skill.",
            "Use the benchmark task, expectations, required headings, and the candidate answer below.",
        ],
        shared_rules=[
            "Be strict about contract adherence and avoid rewarding generic filler.",
        ],
        dimensions=[
            BenchmarkJudgeDimension(
                name="task_fit",
                description="Does the answer perform the requested task rather than drifting into meta commentary or the wrong mode?",
            ),
            BenchmarkJudgeDimension(
                name="contract_adherence",
                description="Does the answer follow the required structure, headings, and explicit benchmark output contract?",
            ),
            BenchmarkJudgeDimension(
                name="expectation_coverage",
                description="Does the answer cover the must-cover expectations and avoid obvious must-avoid failures?",
            ),
            BenchmarkJudgeDimension(
                name="actionability",
                description="Is the answer concrete enough that a downstream user could act on it without major reinterpretation?",
            ),
        ],
        pass_guidance="Set passed=true only if the output is broadly benchmark-worthy, not merely acceptable.",
        include_rule_evaluation=True,
    )
