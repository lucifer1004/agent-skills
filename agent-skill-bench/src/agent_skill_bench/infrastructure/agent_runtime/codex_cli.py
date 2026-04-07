"""Codex CLI runtime adapter."""

from __future__ import annotations

from dataclasses import dataclass, replace
import json
import os
from pathlib import Path
import shutil
import subprocess
from tempfile import TemporaryDirectory
from typing import ContextManager

from agent_skill_bench.infrastructure.skills import (
    resolve_skill_directory,
    skill_dir_name,
    unique_skill_target,
)

from ._workspace import PreparedWorkspace, prepare_workspace
from .base import AgentRunResult, AgentRunSpec, AgentRuntimeError
from .schema import parse_and_validate_json_output


@dataclass(slots=True)
class CodexCLIAgentRuntime:
    """Agent runtime backed by the official Codex CLI."""

    cwd: Path | None = None
    instructions: str | None = None
    timeout_seconds: float | None = None
    cli_path: str | None = None
    model: str | None = None
    name: str = "codex"

    def run(self, spec: AgentRunSpec) -> AgentRunResult:
        """Execute one runtime spec with Codex CLI."""

        timeout_seconds = self.timeout_seconds or spec.timeout_seconds
        workspace_spec = replace(spec, skill_paths=[])
        with prepare_workspace(
            workspace_spec,
            fixed_cwd=self.cwd,
            force_workspace=True,
        ) as workspace:
            if workspace.cwd is None:
                raise AgentRuntimeError(
                    "workspace_materialization_failure",
                    "Codex runtime requires a working directory.",
                )

            instructions = _merge_instructions(spec.runtime_instructions, self.instructions)
            if instructions or spec.skill_paths:
                _write_agents_file(workspace, instructions)

            # [[RFC-0001:C-RUNTIME-EXECUTION]] skill bindings belong to the runtime layer,
            # so Codex benchmark skills must be materialized through the native Codex home
            # rather than downgraded into AGENTS prompt text.
            with TemporaryDirectory(prefix="agent-skill-bench-codex-") as tmp_dir, _native_codex_home(
                spec
            ) as native_codex_home:
                tmp_path = Path(tmp_dir)
                output_path = tmp_path / "codex-output.txt"
                env = os.environ.copy()
                env.update(workspace.env)
                if native_codex_home is not None:
                    env["CODEX_HOME"] = str(native_codex_home.root)
                cmd = self._build_command(
                    cwd=workspace.cwd,
                    output_path=output_path,
                    sandbox_mode="workspace-write" if spec.allowed_tools else "read-only",
                    schema_path=_write_schema(tmp_path, spec.output_schema),
                )
                try:
                    completed = subprocess.run(
                        cmd,
                        capture_output=True,
                        text=True,
                        timeout=timeout_seconds,
                        env=env,
                        input=spec.prompt,
                    )
                except subprocess.TimeoutExpired as exc:
                    raise AgentRuntimeError(
                        "runtime_timeout",
                        f"Codex runtime timed out after {timeout_seconds} seconds."
                    ) from exc

                if completed.returncode != 0:
                    raise AgentRuntimeError(
                        "runtime_transport_failure",
                        f"Codex runtime failed with exit code {completed.returncode}. "
                        f"stdout:\n{completed.stdout.strip()}\n\nstderr:\n{completed.stderr.strip()}"
                    )

                output_text = (
                    output_path.read_text(encoding="utf-8") if output_path.is_file() else ""
                )

            try:
                events = _parse_jsonl_events(completed.stdout)
            except json.JSONDecodeError as exc:
                raise AgentRuntimeError(
                    "runtime_transport_failure",
                    "Codex runtime returned an invalid JSON event stream.",
                ) from exc
            metadata = dict(spec.metadata)
            metadata.update(
                {
                    "cwd": str(workspace.cwd),
                    "json_event_count": len(events),
                    "stderr_chars": len(completed.stderr or ""),
                    "final_output_source": "output_last_message_file",
                }
            )

            if native_codex_home is not None and native_codex_home.installed_skills:
                metadata["injected_skills"] = ",".join(native_codex_home.installed_skills)
                metadata["injected_skill_count"] = len(native_codex_home.installed_skills)
                metadata["skill_binding_mode"] = "native_codex_home"
                metadata["skill_binding_evidence"] = "runtime_metadata.codex_home_skills"
                metadata["codex_home"] = str(native_codex_home.root)
                metadata["codex_skills_root"] = str(native_codex_home.skills_root)
            if workspace.generated_agents_path is not None:
                metadata["agents_path"] = str(workspace.generated_agents_path)

            thread_id = _event_thread_id(events)
            if thread_id is not None:
                metadata["thread_id"] = thread_id
            usage = _event_usage(events)
            if usage is not None:
                for key, value in usage.items():
                    if isinstance(value, (str, int, float, bool)):
                        metadata[f"usage_{key}"] = value
            if spec.output_schema is not None:
                metadata["schema_enforced"] = True

            parsed_output = None
            if spec.output_schema is not None:
                parsed_output = parse_and_validate_json_output(output_text, spec.output_schema)
            return AgentRunResult(
                output_text=output_text,
                parsed_output=parsed_output,
                raw_response=events,
                metadata=metadata,
            )

    def _build_command(
        self,
        *,
        cwd: Path,
        output_path: Path,
        sandbox_mode: str,
        schema_path: Path | None,
    ) -> list[str]:
        """Build the stable Codex CLI invocation."""

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
        ]
        if schema_path is not None:
            cmd.extend(["--output-schema", str(schema_path)])
        if self.model is not None:
            cmd.extend(["--model", self.model])
        cmd.append("-")
        return cmd


def _merge_instructions(*parts: str | None) -> str | None:
    """Merge multiple instruction blocks into one runtime instruction string."""

    lines = [part.strip() for part in parts if part and part.strip()]
    if not lines:
        return None
    return "\n\n".join(lines)


def _write_agents_file(workspace: PreparedWorkspace, instructions: str | None) -> None:
    """Materialize benchmark harness instructions for Codex."""

    if workspace.cwd is None:
        raise AgentRuntimeError(
            "workspace_materialization_failure",
            "Cannot generate AGENTS.md without a working directory.",
        )

    lines = [
        "# Benchmark Harness Instructions",
        "",
        "- Follow the benchmark prompt and context exactly.",
        "- Do not mention this harness file in the answer.",
        "- Return only the final answer for the benchmark run.",
    ]

    if instructions:
        lines.extend(["", "## Runtime Instructions", "", instructions])

    agents_path = workspace.cwd / "AGENTS.md"
    agents_path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
    workspace.generated_agents_path = agents_path


def _write_schema(tmp_path: Path, output_schema: dict[str, object] | None) -> Path | None:
    """Persist the output schema when one is requested."""

    if output_schema is None:
        return None
    schema_path = tmp_path / "output-schema.json"
    schema_path.write_text(json.dumps(output_schema, indent=2), encoding="utf-8")
    return schema_path


def _parse_jsonl_events(stdout_text: str) -> list[dict[str, object]]:
    """Parse Codex JSONL output into structured event payloads."""

    events: list[dict[str, object]] = []
    for line in stdout_text.splitlines():
        if not line.strip():
            continue
        events.append(json.loads(line))
    return events


def _event_thread_id(events: list[dict[str, object]]) -> str | None:
    """Extract the first thread id reported by Codex."""

    for event in events:
        thread_id = event.get("thread_id")
        if isinstance(thread_id, str):
            return thread_id
    return None


def _event_usage(events: list[dict[str, object]]) -> dict[str, object] | None:
    """Extract the final usage block reported by Codex."""

    for event in reversed(events):
        usage = event.get("usage")
        if isinstance(usage, dict):
            return usage
    return None


@dataclass(slots=True)
class NativeCodexHome:
    """One isolated native Codex home prepared for a benchmark run."""

    root: Path
    skills_root: Path
    installed_skills: list[str]


@dataclass(slots=True)
class _NullContext:
    """Small context-manager helper for optional native Codex homes."""

    value: NativeCodexHome | None

    def __enter__(self) -> NativeCodexHome | None:
        return self.value

    def __exit__(self, exc_type, exc, tb) -> None:
        return None


def _native_codex_home(spec: AgentRunSpec) -> ContextManager[NativeCodexHome | None]:
    """Create an isolated native Codex home when benchmark skills are injected."""

    if not spec.skill_paths:
        return _NullContext(None)
    return _CodexHomeContext(spec)


class _CodexHomeContext:
    """Context manager that seeds an isolated Codex home for benchmark skills."""

    def __init__(self, spec: AgentRunSpec) -> None:
        self._spec = spec
        self._tmp_dir: TemporaryDirectory[str] | None = None

    def __enter__(self) -> NativeCodexHome:
        self._tmp_dir = TemporaryDirectory(prefix="agent-skill-bench-codex-home-")
        root = Path(self._tmp_dir.__enter__())
        _seed_codex_home(root)
        skills_root = root / "skills"
        installed_skills = _install_skills_into_root(self._spec.skill_paths, skills_root)
        return NativeCodexHome(
            root=root,
            skills_root=skills_root,
            installed_skills=installed_skills,
        )

    def __exit__(self, exc_type, exc, tb) -> None:
        if self._tmp_dir is not None:
            self._tmp_dir.__exit__(exc_type, exc, tb)
            self._tmp_dir = None
        return None


def _seed_codex_home(target_root: Path) -> None:
    """Seed an isolated Codex home with the minimum persistent user state."""

    source_root = _resolve_codex_home()
    target_root.mkdir(parents=True, exist_ok=True)
    for relative_path in ("auth.json", "config.toml"):
        source_path = source_root / relative_path
        if source_path.is_file():
            shutil.copy2(source_path, target_root / relative_path)


def _resolve_codex_home() -> Path:
    """Resolve the user's active Codex home."""

    configured = os.environ.get("CODEX_HOME")
    if configured:
        return Path(configured).expanduser()
    return Path.home() / ".codex"


def _install_skills_into_root(skill_paths: list[Path], skills_root: Path) -> list[str]:
    """Materialize benchmark skills into a native Codex skills directory."""

    skills_root.mkdir(parents=True, exist_ok=True)
    installed_skills: list[str] = []
    for index, source_path in enumerate(skill_paths, start=1):
        try:
            source_dir = resolve_skill_directory(source_path)
            target_dir = unique_skill_target(skills_root, skill_dir_name(source_dir, index))
            shutil.copytree(source_dir, target_dir, dirs_exist_ok=True)
            installed_skills.append(target_dir.name)
        except Exception as exc:
            raise AgentRuntimeError(
                "workspace_materialization_failure",
                f"Failed to materialize benchmark skill into native Codex home from {source_path}.",
            ) from exc
    return installed_skills
