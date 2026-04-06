"""Codex CLI runtime adapter."""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import subprocess
from tempfile import TemporaryDirectory

from ._workspace import PreparedWorkspace, prepare_workspace
from .base import AgentRunResult, AgentRunSpec
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
        with prepare_workspace(
            spec,
            fixed_cwd=self.cwd,
            force_workspace=True,
            skills_subdir=".agent-skill-bench/skills",
        ) as workspace:
            if workspace.cwd is None:
                raise RuntimeError("Codex runtime requires a working directory.")

            instructions = _merge_instructions(spec.runtime_instructions, self.instructions)
            if instructions or workspace.installed_skills:
                _write_agents_file(workspace, instructions)

            with TemporaryDirectory(prefix="agent-skill-bench-codex-") as tmp_dir:
                tmp_path = Path(tmp_dir)
                output_path = tmp_path / "codex-output.txt"
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
                        env=dict(workspace.env) if workspace.env else None,
                        input=spec.prompt,
                    )
                except subprocess.TimeoutExpired as exc:
                    raise TimeoutError(
                        f"Codex runtime timed out after {timeout_seconds} seconds."
                    ) from exc

                if completed.returncode != 0:
                    raise RuntimeError(
                        f"Codex runtime failed with exit code {completed.returncode}. "
                        f"stdout:\n{completed.stdout.strip()}\n\nstderr:\n{completed.stderr.strip()}"
                    )

                output_text = (
                    output_path.read_text(encoding="utf-8") if output_path.is_file() else ""
                )

            events = _parse_jsonl_events(completed.stdout)
            metadata = dict(spec.metadata)
            metadata.update(
                {
                    "cwd": str(workspace.cwd),
                    "json_event_count": len(events),
                    "stderr_chars": len(completed.stderr or ""),
                    "final_output_source": "output_last_message_file",
                }
            )

            if workspace.installed_skills:
                metadata["injected_skills"] = ",".join(workspace.installed_skills)
                metadata["injected_skill_count"] = len(workspace.installed_skills)
                metadata["skill_binding_mode"] = "workspace_agents"
                metadata["skill_binding_evidence"] = "runtime_metadata.generated_agents"
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
    """Materialize a runtime-specific AGENTS.md for Codex."""

    if workspace.cwd is None:
        raise RuntimeError("Cannot generate AGENTS.md without a working directory.")

    lines = [
        "# Benchmark Harness Instructions",
        "",
        "- Follow the benchmark prompt and context exactly.",
        "- Do not mention this harness file in the answer.",
        "- Return only the final answer for the benchmark run.",
    ]

    if instructions:
        lines.extend(["", "## Runtime Instructions", "", instructions])

    skills_root = workspace.cwd / ".agent-skill-bench" / "skills"
    if workspace.installed_skills:
        lines.extend(
            [
                "",
                "## Injected Benchmark Skills",
                "",
                "The following skills were explicitly injected for this benchmark run.",
                "Treat their SKILL.md files as authoritative task instructions.",
            ]
        )
        for skill_name in workspace.installed_skills:
            skill_file = skills_root / skill_name / "SKILL.md"
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
