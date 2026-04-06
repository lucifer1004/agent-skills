"""Shared agent runtime interfaces."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal, Protocol

ScalarMetadata = str | int | float | bool


@dataclass(slots=True)
class AgentRunSpec:
    """Standardized runtime request shared by candidate and judge runs."""

    purpose: Literal["candidate", "judge"]
    prompt: str
    base_cwd: Path | None = None
    use_temp_cwd: bool = False
    copy_base_cwd: bool = False
    skill_paths: list[Path] = field(default_factory=list)
    runtime_instructions: str | None = None
    setting_sources: tuple[str, ...] = ()
    allowed_tools: tuple[str, ...] = ()
    max_turns: int | None = None
    timeout_seconds: float | None = None
    output_schema: dict[str, object] | None = None
    metadata: dict[str, ScalarMetadata] = field(default_factory=dict)


@dataclass(slots=True)
class AgentRunResult:
    """Normalized output from one agent runtime run."""

    output_text: str
    parsed_output: object | None = None
    raw_response: object | None = None
    metadata: dict[str, ScalarMetadata] = field(default_factory=dict)


class AgentRuntime(Protocol):
    """Minimal runtime interface for benchmark execution."""

    name: str

    def run(self, spec: AgentRunSpec) -> AgentRunResult:
        """Execute one runtime spec and return normalized output."""
