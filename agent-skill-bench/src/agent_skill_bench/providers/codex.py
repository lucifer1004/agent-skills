"""Codex CLI provider adapter."""

from __future__ import annotations

from contextlib import ExitStack, contextmanager
from dataclasses import dataclass, field
import json
import logging
from pathlib import Path
import shutil
import subprocess
from tempfile import TemporaryDirectory

from agent_skill_bench.fixtures import ResolvedBenchmarkCase

from ._skill_utils import resolve_skill_directory, skill_dir_name, unique_skill_target
from .base import ProviderRunResponse

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class CodexExecutionContext:
    """Resolved execution context for one Codex benchmark run."""

    cwd: Path | None
    env: dict[str, str]
    installed_skills: list[str] = field(default_factory=list)
    generated_agents_path: Path | None = None


@dataclass(slots=True)
class CodexCLIProvider:
    """Provider backed by the official Codex CLI."""

    cwd: Path | None = None
    system_prompt: str | None = None
    max_turns: int | None = None
    timeout_seconds: float | None = None
    cli_path: str | None = None
    model: str | None = None
    name: str = "codex"

    def run_case(self, case: ResolvedBenchmarkCase) -> ProviderRunResponse:
        timeout_seconds = self.timeout_seconds or case.execution_profile.timeout_seconds
        logger.info(
            "Starting Codex benchmark run: suite_id=%s case_id=%s mode=%s kind=%s profile=%s",
            case.suite_id,
            case.id,
            case.mode.value,
            case.kind.value,
            case.execution_profile.name,
        )

        with self._prepare_execution_context(case) as execution_context:
            rendered_prompt = case.render_prompt()
            output_path = execution_context.cwd / ".agent-skill-bench" / "codex-last-message.txt"
            output_path.parent.mkdir(parents=True, exist_ok=True)
            self._write_agents_file(execution_context, case)

            cmd = self._build_command(
                case=case,
                cwd=execution_context.cwd,
                output_path=output_path,
            )
            logger.debug("Codex command: %s", cmd)
            try:
                completed = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    timeout=timeout_seconds,
                    env=execution_context.env or None,
                    input=rendered_prompt,
                )
            except subprocess.TimeoutExpired as exc:
                logger.error(
                    "Codex benchmark run timed out: case_id=%s timeout_seconds=%s",
                    case.id,
                    timeout_seconds,
                )
                raise RuntimeError(
                    f"Codex benchmark run timed out for case '{case.id}' after "
                    f"{timeout_seconds} seconds."
                ) from exc

            if completed.returncode != 0:
                stderr = completed.stderr.strip()
                raise RuntimeError(
                    f"Codex benchmark run failed for case '{case.id}' with exit code "
                    f"{completed.returncode}. stderr:\n{stderr}"
                )

            output_text = output_path.read_text(encoding="utf-8") if output_path.is_file() else ""
            events = _parse_jsonl_events(completed.stdout)
            metadata: dict[str, str | int | float | bool] = {
                "case_id": case.id,
                "suite_id": case.suite_id,
                "provider": self.name,
                "profile": case.execution_profile.name,
                "cwd": str(execution_context.cwd),
                "json_event_count": len(events),
                "stderr_chars": len(completed.stderr or ""),
                "final_output_source": "output_last_message_file",
            }
            thread_id = _event_thread_id(events)
            if thread_id is not None:
                metadata["thread_id"] = thread_id
            usage = _event_usage(events)
            if usage is not None:
                for key, value in usage.items():
                    if isinstance(value, (str, int, float, bool)):
                        metadata[f"usage_{key}"] = value
            if execution_context.installed_skills:
                metadata["injected_skills"] = ",".join(execution_context.installed_skills)
                metadata["injected_skill_count"] = len(execution_context.installed_skills)
                metadata["skill_binding_mode"] = "workspace_agents"
                metadata["skill_binding_evidence"] = "provider_metadata.generated_agents"
            if execution_context.generated_agents_path is not None:
                metadata["agents_path"] = str(execution_context.generated_agents_path)

            logger.info(
                "Codex benchmark run completed: case_id=%s output_chars=%s events=%s",
                case.id,
                len(output_text),
                len(events),
            )
            return ProviderRunResponse(
                output_text=output_text,
                raw_response=events,
                metadata=metadata,
            )

    def _build_command(
        self,
        *,
        case: ResolvedBenchmarkCase,
        cwd: Path,
        output_path: Path,
    ) -> list[str]:
        """Build the stable Codex CLI invocation for one benchmark run."""

        sandbox_mode = "read-only"
        if case.execution_profile.allowed_tools:
            sandbox_mode = "workspace-write"

        cmd = [
            self.cli_path or "codex",
            "exec",
            "--json",
            "--skip-git-repo-check",
            "--sandbox",
            sandbox_mode,
            "--cd",
            str(cwd),
            "--output-last-message",
            str(output_path),
            "-",
        ]
        if self.model is not None:
            cmd.extend(["--model", self.model])
        return cmd

    @contextmanager
    def _prepare_execution_context(
        self,
        case: ResolvedBenchmarkCase,
    ) -> CodexExecutionContext:
        """Create the isolated working context for one benchmark case."""

        with ExitStack() as stack:
            execution_context = CodexExecutionContext(cwd=None, env={})

            if self.cwd is not None:
                execution_context.cwd = self.cwd
                self._install_skills(case.skill_paths, execution_context)
                yield execution_context
                return

            fixture_cwd = case.resolve_working_dir()
            if fixture_cwd is not None:
                if case.execution_profile.copy_repo_to_temp:
                    copied_repo = Path(
                        stack.enter_context(
                            TemporaryDirectory(prefix="agent-skill-bench-repo-")
                        )
                    ) / fixture_cwd.name
                    shutil.copytree(fixture_cwd, copied_repo, dirs_exist_ok=True)
                    execution_context.cwd = copied_repo
                else:
                    execution_context.cwd = fixture_cwd
                self._install_skills(case.skill_paths, execution_context)
                yield execution_context
                return

            execution_context.cwd = Path(
                stack.enter_context(
                    TemporaryDirectory(prefix="agent-skill-bench-cwd-")
                )
            )
            self._install_skills(case.skill_paths, execution_context)
            yield execution_context

    def _install_skills(
        self,
        skill_paths: list[Path],
        execution_context: CodexExecutionContext,
    ) -> None:
        """Copy explicit benchmark skills into the temporary Codex workspace."""

        if not skill_paths:
            return
        if execution_context.cwd is None:
            raise RuntimeError("Cannot inject skills without a working directory.")

        skills_root = execution_context.cwd / ".agent-skill-bench" / "skills"
        skills_root.mkdir(parents=True, exist_ok=True)

        installed_skills: list[str] = []
        for index, source_path in enumerate(skill_paths, start=1):
            source_dir = resolve_skill_directory(source_path)
            target_dir = unique_skill_target(skills_root, skill_dir_name(source_dir, index))
            shutil.copytree(source_dir, target_dir, dirs_exist_ok=True)
            installed_skills.append(target_dir.name)

        execution_context.installed_skills.extend(installed_skills)

    def _write_agents_file(
        self,
        execution_context: CodexExecutionContext,
        case: ResolvedBenchmarkCase,
    ) -> None:
        """Materialize a benchmark-specific AGENTS.md for Codex."""

        if execution_context.cwd is None:
            raise RuntimeError("Cannot generate AGENTS.md without a working directory.")

        lines = [
            "# Benchmark Harness Instructions",
            "",
            "- Follow the benchmark user request and context exactly.",
            "- Do not mention this harness file in the answer.",
            "- Return only the final answer for the benchmark case.",
        ]

        if self.system_prompt:
            lines.extend(
                [
                    "",
                    "## Additional Provider Instructions",
                    "",
                    self.system_prompt.strip(),
                ]
            )

        skills_root = execution_context.cwd / ".agent-skill-bench" / "skills"
        if execution_context.installed_skills:
            lines.extend(
                [
                    "",
                    "## Injected Benchmark Skills",
                    "",
                    "The following skills were explicitly injected for this benchmark run.",
                    "Treat their SKILL.md files as authoritative task instructions.",
                ]
            )
            for skill_name in execution_context.installed_skills:
                skill_dir = skills_root / skill_name
                skill_file = skill_dir / "SKILL.md"
                lines.extend(
                    [
                        "",
                        f"### Skill: {skill_name}",
                        "",
                        f"Skill path: {skill_file}",
                        "",
                        skill_file.read_text(encoding="utf-8").strip(),
                    ]
                )

        agents_path = execution_context.cwd / "AGENTS.md"
        agents_path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
        execution_context.generated_agents_path = agents_path


def _parse_jsonl_events(stdout_text: str) -> list[dict[str, object]]:
    """Parse Codex JSONL output into structured event payloads."""

    events: list[dict[str, object]] = []
    for line in stdout_text.splitlines():
        if not line.strip():
            continue
        events.append(json.loads(line))
    return events


def _event_thread_id(events: list[dict[str, object]]) -> str | None:
    """Extract a thread id from Codex JSONL events when present."""

    for event in events:
        thread_id = event.get("thread_id")
        if isinstance(thread_id, str):
            return thread_id
    return None


def _event_usage(events: list[dict[str, object]]) -> dict[str, object] | None:
    """Extract final usage from turn-completed events when present."""

    for event in reversed(events):
        usage = event.get("usage")
        if isinstance(usage, dict):
            return usage
    return None
