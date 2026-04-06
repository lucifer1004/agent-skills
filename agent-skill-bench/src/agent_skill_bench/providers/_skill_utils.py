"""Shared helpers for provider-side skill materialization."""

from __future__ import annotations

from pathlib import Path


def resolve_skill_directory(source_path: Path) -> Path:
    """Normalize a skill input path to the directory that contains SKILL.md."""

    if source_path.is_dir():
        skill_dir = source_path
    elif source_path.name == "SKILL.md":
        skill_dir = source_path.parent
    else:
        raise ValueError(
            f"Skill path must be a skill directory or a SKILL.md file, got: {source_path}"
        )

    skill_file = skill_dir / "SKILL.md"
    if not skill_file.is_file():
        raise ValueError(f"Skill path does not contain SKILL.md: {source_path}")
    return skill_dir


def skill_dir_name(skill_dir: Path, index: int) -> str:
    """Derive a stable local directory name for one injected skill."""

    name = skill_dir.name.strip()
    if name:
        return name
    return f"skill-{index}"


def unique_skill_target(skills_root: Path, base_name: str) -> Path:
    """Allocate a unique local skill directory without clobbering prior copies."""

    candidate = skills_root / base_name
    if not candidate.exists():
        return candidate

    suffix = 2
    while True:
        candidate = skills_root / f"{base_name}-{suffix}"
        if not candidate.exists():
            return candidate
        suffix += 1
