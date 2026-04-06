"""Provider abstractions and registry for benchmark execution."""

from .base import BenchmarkProvider, ProviderRunResponse
from .claude import ClaudeAgentSDKProvider
from .codex import CodexCLIProvider
from .mock import MockBenchmarkProvider


def get_provider(name: str, **kwargs: object) -> BenchmarkProvider:
    """Return a built-in provider by name."""

    if name == "mock":
        return MockBenchmarkProvider()
    if name == "claude":
        return ClaudeAgentSDKProvider(**kwargs)
    if name == "codex":
        return CodexCLIProvider(**kwargs)
    raise ValueError(f"Unknown provider {name!r}.")


__all__ = [
    "BenchmarkProvider",
    "ClaudeAgentSDKProvider",
    "CodexCLIProvider",
    "MockBenchmarkProvider",
    "ProviderRunResponse",
    "get_provider",
]
