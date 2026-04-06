"""Shared workspace preparation helpers for agent runtimes."""

from __future__ import annotations

from contextlib import ExitStack, contextmanager
from dataclasses import dataclass, field
from pathlib import Path
import shutil
from tempfile import TemporaryDirectory
from typing import Iterator

from agent_skill_bench.infrastructure.skills import (
    resolve_skill_directory,
    skill_dir_name,
    unique_skill_target,
)

from .base import AgentRunSpec, AgentRuntimeError


@dataclass(slots=True)
class PreparedWorkspace:
    """Resolved workspace state for one runtime run."""

    cwd: Path | None
    env: dict[str, str]
    installed_skills: list[str] = field(default_factory=list)
    generated_agents_path: Path | None = None


@contextmanager
def prepare_workspace(
    spec: AgentRunSpec,
    *,
    fixed_cwd: Path | None = None,
    isolate_home: bool = False,
    force_workspace: bool = False,
    skills_subdir: str | None = None,
) -> Iterator[PreparedWorkspace]:
    """Create an isolated workspace for one runtime run."""

    with ExitStack() as stack:
        workspace = PreparedWorkspace(cwd=None, env={})

        if isolate_home:
            home_dir = Path(stack.enter_context(TemporaryDirectory(prefix="agent-skill-bench-home-")))
            workspace.env["HOME"] = str(home_dir)

        if fixed_cwd is not None:
            workspace.cwd = fixed_cwd
        elif spec.base_cwd is not None:
            if spec.copy_base_cwd:
                copied_root = Path(
                    stack.enter_context(TemporaryDirectory(prefix="agent-skill-bench-repo-"))
                ) / spec.base_cwd.name
                shutil.copytree(spec.base_cwd, copied_root, dirs_exist_ok=True)
                workspace.cwd = copied_root
            else:
                workspace.cwd = spec.base_cwd
        elif spec.use_temp_cwd or spec.skill_paths or force_workspace:
            workspace.cwd = Path(
                stack.enter_context(TemporaryDirectory(prefix="agent-skill-bench-cwd-"))
            )

        if spec.skill_paths:
            if workspace.cwd is None or skills_subdir is None:
                raise AgentRuntimeError(
                    "workspace_materialization_failure",
                    "Cannot inject benchmark skills without a runtime workspace.",
                )
            _install_skills(spec.skill_paths, workspace, skills_subdir)

        yield workspace


def _install_skills(
    skill_paths: list[Path],
    workspace: PreparedWorkspace,
    skills_subdir: str,
) -> None:
    """Materialize benchmark-provided skills into the runtime workspace."""

    if workspace.cwd is None:
        raise AgentRuntimeError(
            "workspace_materialization_failure",
            "Cannot install benchmark skills without a runtime workspace.",
        )

    skills_root = workspace.cwd / skills_subdir
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
                f"Failed to materialize benchmark skill from {source_path}.",
            ) from exc

    workspace.installed_skills.extend(installed_skills)
