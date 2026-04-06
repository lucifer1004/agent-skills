"""Composition helpers for built-in agent runtimes."""

from __future__ import annotations

from agent_skill_bench.infrastructure.agent_runtime import (
    AgentRuntime,
    ClaudeSDKAgentRuntime,
    CodexCLIAgentRuntime,
    MockAgentRuntime,
)


def get_runtime(name: str, **kwargs: object) -> AgentRuntime:
    """Return a built-in runtime adapter by name."""

    normalized_kwargs = {key: value for key, value in kwargs.items() if value is not None}
    if name == "mock":
        if normalized_kwargs:
            raise ValueError(
                f"Runtime {name!r} does not accept options: {sorted(normalized_kwargs)}"
            )
        return MockAgentRuntime()
    if name == "claude":
        return ClaudeSDKAgentRuntime(**normalized_kwargs)
    if name == "codex":
        return CodexCLIAgentRuntime(**normalized_kwargs)
    raise ValueError(f"Unknown runtime {name!r}.")
