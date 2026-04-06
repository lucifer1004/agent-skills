"""Claude Agent SDK runtime adapter."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ._workspace import prepare_workspace
from .base import AgentRunResult, AgentRunSpec
from .schema import parse_and_validate_json_output


@dataclass(slots=True)
class ClaudeSDKAgentRuntime:
    """Agent runtime backed by Anthropic's Claude Agent SDK for Python."""

    cwd: Path | None = None
    instructions: str | None = None
    max_turns: int | None = None
    timeout_seconds: float | None = None
    cli_path: str | None = None
    isolate_home: bool = False
    name: str = "claude"

    def run(self, spec: AgentRunSpec) -> AgentRunResult:
        """Execute one runtime spec with the Claude SDK."""

        timeout_seconds = self.timeout_seconds or spec.timeout_seconds
        try:
            coroutine = self._run_async(spec)
            if timeout_seconds is None:
                return asyncio.run(coroutine)
            return asyncio.run(asyncio.wait_for(coroutine, timeout=timeout_seconds))
        except TimeoutError as exc:
            raise RuntimeError(
                f"Claude runtime timed out for {spec.purpose} after {timeout_seconds} seconds."
            ) from exc

    async def _run_async(self, spec: AgentRunSpec) -> AgentRunResult:
        """Run one runtime spec asynchronously through the Claude SDK."""

        sdk = _import_claude_agent_sdk()
        with prepare_workspace(
            spec,
            fixed_cwd=self.cwd,
            isolate_home=self.isolate_home,
            skills_subdir=".claude/skills",
        ) as workspace:
            stderr_lines: list[str] = []
            init_data: dict[str, Any] | None = None
            options = self._build_options(
                sdk=sdk,
                spec=spec,
                workspace_cwd=workspace.cwd,
                env=workspace.env,
                stderr_lines=stderr_lines,
            )
            assistant_chunks: list[str] = []
            result_text: str | None = None
            assistant_message_count = 0
            message_count = 0

            try:
                async for message in sdk.query(prompt=spec.prompt, options=options):
                    message_count += 1
                    init_data = init_data or _extract_init_data(message, sdk)
                    message_assistant_chunks = _extract_assistant_text(message, sdk)
                    if message_assistant_chunks:
                        assistant_message_count += 1
                        assistant_chunks.extend(message_assistant_chunks)
                    message_result = _extract_result_text(message)
                    if message_result is not None:
                        result_text = message_result
            except Exception as exc:
                if stderr_lines:
                    stderr_text = "\n".join(stderr_lines)
                    raise RuntimeError(
                        f"Claude runtime failed during {spec.purpose}. CLI stderr:\n{stderr_text}"
                    ) from exc
                raise

            assistant_text = "\n".join(
                chunk for chunk in assistant_chunks if isinstance(chunk, str) and chunk.strip()
            )
            if result_text is not None:
                output_text = result_text
                final_output_source = "result"
            else:
                output_text = assistant_text
                final_output_source = "assistant_fallback"

            parsed_output = None
            if spec.output_schema is not None:
                parsed_output = parse_and_validate_json_output(output_text, spec.output_schema)

            metadata = dict(spec.metadata)
            metadata.update(
                {
                    "message_count": message_count,
                    "assistant_message_count": assistant_message_count,
                    "assistant_text_chars": len(assistant_text),
                    "result_text_chars": len(result_text) if result_text is not None else 0,
                    "final_output_source": final_output_source,
                    "isolate_home": self.isolate_home,
                }
            )
            if workspace.cwd is not None:
                metadata["cwd"] = str(workspace.cwd)
            if "HOME" in workspace.env:
                metadata["home"] = workspace.env["HOME"]
            if workspace.installed_skills:
                metadata["injected_skills"] = ",".join(workspace.installed_skills)
                metadata["injected_skill_count"] = len(workspace.installed_skills)
            if init_data is not None:
                available_skills = init_data.get("skills")
                slash_commands = init_data.get("slash_commands")
                if isinstance(available_skills, list):
                    metadata["available_skills"] = ",".join(str(skill) for skill in available_skills)
                    if workspace.installed_skills:
                        metadata["registered_injected_skills"] = ",".join(
                            skill
                            for skill in workspace.installed_skills
                            if skill in available_skills
                        )
                        metadata["registered_injected_skill_count"] = sum(
                            1
                            for skill in workspace.installed_skills
                            if skill in available_skills
                        )
                if isinstance(slash_commands, list):
                    metadata["available_slash_commands"] = ",".join(
                        str(command) for command in slash_commands
                    )
            if spec.output_schema is not None:
                metadata["schema_enforced"] = True

            return AgentRunResult(
                output_text=output_text,
                parsed_output=parsed_output,
                metadata=metadata,
            )

    def _build_options(
        self,
        *,
        sdk: Any,
        spec: AgentRunSpec,
        workspace_cwd: Path | None,
        env: dict[str, str],
        stderr_lines: list[str],
    ) -> Any | None:
        """Build Claude SDK options for one runtime run."""

        option_kwargs: dict[str, Any] = {}
        if workspace_cwd is not None:
            option_kwargs["cwd"] = str(workspace_cwd)

        system_prompt = _merge_instructions(spec.runtime_instructions, self.instructions)
        if system_prompt is not None:
            option_kwargs["system_prompt"] = system_prompt

        max_turns = self.max_turns if self.max_turns is not None else spec.max_turns
        if max_turns is not None:
            option_kwargs["max_turns"] = max_turns
        if self.cli_path is not None:
            option_kwargs["cli_path"] = self.cli_path
        if env:
            option_kwargs["env"] = env

        option_kwargs["setting_sources"] = list(spec.setting_sources)
        option_kwargs["extra_args"] = {"strict-mcp-config": None}
        option_kwargs["tools"] = list(spec.allowed_tools)
        option_kwargs["stderr"] = _build_stderr_callback(stderr_lines)
        return sdk.ClaudeAgentOptions(**option_kwargs)


def _merge_instructions(*parts: str | None) -> str | None:
    """Merge multiple instruction blocks into one system prompt."""

    lines = [part.strip() for part in parts if part and part.strip()]
    if not lines:
        return None
    return "\n\n".join(lines)


def _build_stderr_callback(stderr_lines: list[str]) -> Any:
    """Collect Claude CLI stderr lines."""

    def _handle_stderr(line: str) -> None:
        stderr_lines.append(line)

    return _handle_stderr


def _extract_assistant_text(message: Any, sdk: Any) -> list[str]:
    """Extract assistant text blocks from one SDK message."""

    if not isinstance(message, getattr(sdk, "AssistantMessage")):
        return []
    text_type = getattr(sdk, "TextBlock")
    return [block.text for block in message.content if isinstance(block, text_type)]


def _extract_result_text(message: Any) -> str | None:
    """Extract the terminal result text from one SDK message when present."""

    result = getattr(message, "result", None)
    return result if isinstance(result, str) else None


def _extract_init_data(message: Any, sdk: Any) -> dict[str, Any] | None:
    """Extract system init payloads from Claude SDK messages."""

    if not isinstance(message, getattr(sdk, "SystemMessage")):
        return None
    if getattr(message, "subtype", None) != "init":
        return None
    data = getattr(message, "data", None)
    return data if isinstance(data, dict) else None


def _import_claude_agent_sdk() -> Any:
    """Import the optional Claude Agent SDK dependency."""

    try:
        import claude_agent_sdk  # type: ignore
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError(
            "claude-agent-sdk is required for the Claude SDK runtime. Install it first."
        ) from exc
    return claude_agent_sdk
