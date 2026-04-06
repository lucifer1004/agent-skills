"""Benchmark runner orchestration."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from time import perf_counter
from typing import Iterable

from .fixtures import ResolvedBenchmarkCase, resolve_case
from .providers.base import BenchmarkProvider


@dataclass(slots=True)
class BenchmarkRunConfig:
    """Execution config for a benchmark run."""

    provider_name: str
    suite_filter: str | None = None
    case_ids: set[str] = field(default_factory=set)
    execution_profile: str | None = None
    skill_paths: list[Path] | None = None
    no_skills: bool = False


@dataclass(slots=True)
class SkillBindingSummary:
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
class BenchmarkRunResult:
    """Normalized record for one executed case."""

    case_id: str
    suite_id: str
    provider_name: str
    mode: str
    kind: str
    execution_profile: str
    output_text: str
    duration_seconds: float
    metadata: dict[str, str | int | float | bool] = field(default_factory=dict)
    skill_binding: SkillBindingSummary = field(default_factory=SkillBindingSummary)
    evaluation_profile: str | None = None
    skill_paths: list[str] = field(default_factory=list)
    source_path: Path | None = None

    def to_dict(self) -> dict[str, object]:
        """Convert a run result into a JSON-serializable mapping."""

        return {
            "case_id": self.case_id,
            "suite_id": self.suite_id,
            "provider_name": self.provider_name,
            "mode": self.mode,
            "kind": self.kind,
            "execution_profile": self.execution_profile,
            "evaluation_profile": self.evaluation_profile,
            "skill_paths": list(self.skill_paths),
            "output_text": self.output_text,
            "duration_seconds": self.duration_seconds,
            "metadata": dict(self.metadata),
            "skill_binding": self.skill_binding.to_dict(),
            "source_path": str(self.source_path) if self.source_path else None,
        }


def save_run_results(results: Iterable[BenchmarkRunResult], output_path: str | Path) -> Path:
    """Persist normalized run results to a JSON file."""

    destination = Path(output_path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    payload = [result.to_dict() for result in results]
    destination.write_text(f"{json.dumps(payload, indent=2)}\n", encoding="utf-8")
    return destination


class BenchmarkRunner:
    """Execute resolved cases through a provider and normalize results."""

    def __init__(self, provider: BenchmarkProvider):
        self.provider = provider

    def run_case(self, case: ResolvedBenchmarkCase) -> BenchmarkRunResult:
        """Run one resolved benchmark case."""

        started_at = perf_counter()
        response = self.provider.run_case(case)
        duration = perf_counter() - started_at
        metadata = dict(response.metadata)

        return BenchmarkRunResult(
            case_id=case.id,
            suite_id=case.suite_id,
            provider_name=self.provider.name,
            mode=case.mode.value,
            kind=case.kind.value,
            execution_profile=case.execution_profile.name,
            evaluation_profile=case.evaluation_profile,
            skill_paths=[str(path) for path in case.skill_paths],
            output_text=response.output_text,
            duration_seconds=duration,
            metadata=metadata,
            skill_binding=_summarize_skill_binding(case, metadata),
            source_path=case.source_path,
        )

    def run_case_file(
        self,
        path: str | Path,
        *,
        config: BenchmarkRunConfig | None = None,
    ) -> BenchmarkRunResult:
        """Load, resolve, and execute one case file."""

        selected_config = config or BenchmarkRunConfig(provider_name=self.provider.name)
        resolved = resolve_case(
            path,
            skill_paths=selected_config.skill_paths,
            no_skills=selected_config.no_skills,
            execution_profile_name=selected_config.execution_profile,
        )
        return self.run_case(resolved)

    def run_case_files(
        self,
        paths: Iterable[str | Path],
        *,
        config: BenchmarkRunConfig | None = None,
    ) -> list[BenchmarkRunResult]:
        """Load, filter, and execute multiple case files."""

        selected_config = config or BenchmarkRunConfig(provider_name=self.provider.name)
        results: list[BenchmarkRunResult] = []

        for path in paths:
            resolved = resolve_case(
                path,
                skill_paths=selected_config.skill_paths,
                no_skills=selected_config.no_skills,
                execution_profile_name=selected_config.execution_profile,
            )
            if selected_config.suite_filter and resolved.suite_id != selected_config.suite_filter:
                continue
            if selected_config.case_ids and resolved.id not in selected_config.case_ids:
                continue
            results.append(self.run_case(resolved))

        return results


def _summarize_skill_binding(
    case: ResolvedBenchmarkCase,
    metadata: dict[str, str | int | float | bool],
) -> SkillBindingSummary:
    """Normalize provider metadata into bench-level skill binding semantics."""

    requested_skills = [_requested_skill_name(path) for path in case.skill_paths]
    if not requested_skills:
        return SkillBindingSummary()

    injected_skills = _split_csv_field(metadata.get("injected_skills"))
    registered_skills = _split_csv_field(metadata.get("registered_injected_skills"))

    if injected_skills and registered_skills:
        if set(registered_skills) == set(injected_skills) and len(registered_skills) == len(
            injected_skills
        ):
            status = "registered"
        else:
            status = "partial"
        return SkillBindingSummary(
            requested_skills=requested_skills,
            injected_skills=injected_skills,
            registered_skills=registered_skills,
            registration_status=status,
            registration_confirmed=(status == "registered"),
            registration_evidence="provider_metadata.cli_init",
            usage_confirmed=None,
        )

    if injected_skills:
        return SkillBindingSummary(
            requested_skills=requested_skills,
            injected_skills=injected_skills,
            registration_status="missing",
            registration_confirmed=False,
            registration_evidence="provider_metadata.cli_init",
            usage_confirmed=None,
        )

    return SkillBindingSummary(
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
    """Parse a provider metadata CSV field into a normalized string list."""

    if not isinstance(value, str) or not value:
        return []
    return [item for item in (part.strip() for part in value.split(",")) if item]
