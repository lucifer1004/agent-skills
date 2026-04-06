"""Claude Agent SDK provider adapter."""

from __future__ import annotations

import asyncio
from contextlib import ExitStack, contextmanager
from dataclasses import dataclass, field
import logging
from pathlib import Path
import shutil
from tempfile import TemporaryDirectory
from typing import Any

from agent_skill_bench.fixtures import ResolvedBenchmarkCase

from .base import ProviderRunResponse
from ._skill_utils import resolve_skill_directory, skill_dir_name, unique_skill_target

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class ClaudeExecutionContext:
    """Resolved execution context for one provider run."""

    cwd: Path | None
    env: dict[str, str]
    installed_skills: list[str] = field(default_factory=list)


@dataclass(slots=True)
class ClaudeAgentSDKProvider:
    """Provider backed by Anthropic's Claude Agent SDK for Python."""

    cwd: Path | None = None
    system_prompt: str | None = None
    max_turns: int | None = None
    timeout_seconds: float | None = None
    cli_path: str | None = None
    isolate_home: bool = False
    name: str = "claude"

    def run_case(self, case: ResolvedBenchmarkCase) -> ProviderRunResponse:
        timeout_seconds = self.timeout_seconds or case.execution_profile.timeout_seconds
        logger.info(
            "Starting Claude benchmark run: suite_id=%s case_id=%s mode=%s kind=%s profile=%s",
            case.suite_id,
            case.id,
            case.mode.value,
            case.kind.value,
            case.execution_profile.name,
        )
        try:
            coroutine = self._run_case_async(case)
            if timeout_seconds is None:
                return asyncio.run(coroutine)
            return asyncio.run(asyncio.wait_for(coroutine, timeout=timeout_seconds))
        except TimeoutError as exc:
            logger.error(
                "Claude benchmark run timed out: case_id=%s timeout_seconds=%s",
                case.id,
                timeout_seconds,
            )
            raise RuntimeError(
                f"Claude benchmark run timed out for case '{case.id}' after "
                f"{timeout_seconds} seconds."
            ) from exc

    async def _run_case_async(self, case: ResolvedBenchmarkCase) -> ProviderRunResponse:
        logger.debug("Importing claude-agent-sdk")
        sdk = _import_claude_agent_sdk()
        with self._prepare_execution_context(case) as execution_context:
            stderr_lines: list[str] = []
            init_data: dict[str, Any] | None = None
            options = self._build_options(
                sdk=sdk,
                case=case,
                execution_context=execution_context,
                stderr_lines=stderr_lines,
            )
            assistant_chunks: list[str] = []
            result_text: str | None = None
            assistant_message_count = 0
            message_count = 0
            rendered_prompt = case.render_prompt()

            logger.debug(
                "Claude query prepared: case_id=%s cwd=%s profile=%s system_prompt_set=%s prompt_chars=%s isolate_home=%s skill_count=%s",
                case.id,
                getattr(options, "cwd", None) if options is not None else None,
                case.execution_profile.name,
                bool(self.system_prompt),
                len(rendered_prompt),
                self.isolate_home,
                len(case.skill_paths),
            )

            try:
                logger.info("Calling Claude query(): case_id=%s", case.id)
                async for message in sdk.query(prompt=rendered_prompt, options=options):
                    message_count += 1
                    logger.debug(
                        "Received Claude message: case_id=%s index=%s type=%s",
                        case.id,
                        message_count,
                        type(message).__name__,
                    )
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
                    logger.error("Claude CLI stderr for case_id=%s:\n%s", case.id, stderr_text)
                    raise RuntimeError(
                        f"Claude query failed for case '{case.id}'. CLI stderr:\n{stderr_text}"
                    ) from exc
                logger.exception("Claude query failed: case_id=%s", case.id)
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
            logger.info(
                "Claude benchmark run completed: case_id=%s messages=%s output_chars=%s source=%s",
                case.id,
                message_count,
                len(output_text),
                final_output_source,
            )

            metadata: dict[str, str | int | float | bool] = {
                "case_id": case.id,
                "suite_id": case.suite_id,
                "message_count": message_count,
                "assistant_message_count": assistant_message_count,
                "assistant_text_chars": len(assistant_text),
                "result_text_chars": len(result_text) if result_text is not None else 0,
                "final_output_source": final_output_source,
                "provider": self.name,
                "profile": case.execution_profile.name,
                "isolate_home": self.isolate_home,
            }
            if execution_context.cwd is not None:
                metadata["cwd"] = str(execution_context.cwd)
            if "HOME" in execution_context.env:
                metadata["home"] = execution_context.env["HOME"]
            if execution_context.installed_skills:
                metadata["injected_skills"] = ",".join(execution_context.installed_skills)
                metadata["injected_skill_count"] = len(execution_context.installed_skills)
            if init_data is not None:
                available_skills = init_data.get("skills")
                slash_commands = init_data.get("slash_commands")
                if isinstance(available_skills, list):
                    metadata["available_skills"] = ",".join(
                        str(skill) for skill in available_skills
                    )
                    if execution_context.installed_skills:
                        metadata["registered_injected_skills"] = ",".join(
                            skill
                            for skill in execution_context.installed_skills
                            if skill in available_skills
                        )
                        metadata["registered_injected_skill_count"] = sum(
                            1 for skill in execution_context.installed_skills if skill in available_skills
                        )
                if isinstance(slash_commands, list):
                    metadata["available_slash_commands"] = ",".join(
                        str(command) for command in slash_commands
                    )

            return ProviderRunResponse(output_text=output_text, metadata=metadata)

    def _build_options(
        self,
        *,
        sdk: Any,
        case: ResolvedBenchmarkCase,
        execution_context: ClaudeExecutionContext,
        stderr_lines: list[str],
    ) -> Any | None:
        option_kwargs: dict[str, Any] = {}
        if execution_context.cwd is not None:
            option_kwargs["cwd"] = str(execution_context.cwd)
        if self.system_prompt is not None:
            option_kwargs["system_prompt"] = self.system_prompt

        max_turns = self.max_turns if self.max_turns is not None else case.execution_profile.max_turns
        if max_turns is not None:
            option_kwargs["max_turns"] = max_turns
        if self.cli_path is not None:
            option_kwargs["cli_path"] = self.cli_path
        if execution_context.env:
            option_kwargs["env"] = execution_context.env

        option_kwargs["setting_sources"] = list(case.execution_profile.setting_sources)
        option_kwargs["extra_args"] = _build_extra_args()
        option_kwargs["tools"] = list(case.execution_profile.allowed_tools)
        option_kwargs["stderr"] = _build_stderr_callback(stderr_lines)

        logger.debug("Claude options payload: %s", option_kwargs)
        return sdk.ClaudeAgentOptions(**option_kwargs)

    @contextmanager
    def _prepare_execution_context(
        self,
        case: ResolvedBenchmarkCase,
    ) -> ClaudeExecutionContext:
        """Create the isolated working context for one benchmark case."""

        with ExitStack() as stack:
            execution_context = ClaudeExecutionContext(cwd=None, env={})

            if self.isolate_home:
                home_dir = Path(
                    stack.enter_context(
                        TemporaryDirectory(prefix="agent-skill-bench-home-")
                    )
                )
                execution_context.env["HOME"] = str(home_dir)

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

            if case.execution_profile.use_temp_cwd or case.skill_paths:
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
        execution_context: ClaudeExecutionContext,
    ) -> None:
        """Materialize explicit benchmark skills into the local skill dir."""

        if not skill_paths:
            return
        if execution_context.cwd is None:
            raise RuntimeError("Cannot inject skills without a working directory.")

        skills_root = execution_context.cwd / ".claude" / "skills"
        skills_root.mkdir(parents=True, exist_ok=True)

        installed_skills: list[str] = []
        for index, source_path in enumerate(skill_paths, start=1):
            source_dir = resolve_skill_directory(source_path)
            target_dir = unique_skill_target(skills_root, skill_dir_name(source_dir, index))
            shutil.copytree(source_dir, target_dir, dirs_exist_ok=True)
            installed_skills.append(target_dir.name)

        execution_context.installed_skills.extend(installed_skills)


def _build_extra_args() -> dict[str, str | None]:
    """Build stable CLI flags for isolated benchmark execution."""

    return {
        "strict-mcp-config": None,
    }


def _build_stderr_callback(stderr_lines: list[str]) -> Any:
    """Collect Claude CLI stderr lines while routing them into standard logging."""

    def _handle_stderr(line: str) -> None:
        stderr_lines.append(line)
        logger.warning("Claude CLI stderr: %s", line)

    return _handle_stderr


def _extract_assistant_text(message: Any, sdk: Any) -> list[str]:
    """Extract user-facing text blocks from assistant messages only."""

    chunks: list[str] = []
    assistant_type = getattr(sdk, "AssistantMessage", None)
    text_block_type = getattr(sdk, "TextBlock", None)

    if assistant_type is not None and isinstance(message, assistant_type):
        for block in getattr(message, "content", []):
            if text_block_type is not None and isinstance(block, text_block_type):
                chunks.append(block.text)
    return chunks


def _extract_result_text(message: Any) -> str | None:
    """Extract the final result payload from a result-like message."""

    result = getattr(message, "result", None)
    if isinstance(result, str):
        return result
    return None


def _extract_init_data(message: Any, sdk: Any) -> dict[str, Any] | None:
    """Extract Claude init payloads from system messages when available."""

    system_type = getattr(sdk, "SystemMessage", None)
    if system_type is None or not isinstance(message, system_type):
        return None

    subtype = getattr(message, "subtype", None)
    data = getattr(message, "data", None)
    if subtype != "init" or not isinstance(data, dict):
        return None
    return data


def _import_claude_agent_sdk() -> Any:
    """Import the SDK lazily so the package can still load without it."""

    try:
        import claude_agent_sdk
    except ImportError as exc:  # pragma: no cover - defensive path
        raise RuntimeError(
            "claude-agent-sdk is not installed. Add it to the Pixi/PyPI dependencies "
            "before using the Claude provider."
        ) from exc
    logger.debug("claude-agent-sdk imported successfully")
    return claude_agent_sdk
