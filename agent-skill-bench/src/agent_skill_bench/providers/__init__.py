"""Provider abstractions and registry for benchmark execution."""

from .base import BenchmarkProvider, ProviderRunResponse
from .claude import ClaudeAgentSDKProvider
from .mock import MockBenchmarkProvider


def get_provider(name: str, **kwargs: object) -> BenchmarkProvider:
    """Return a built-in provider by name."""

    if name == "mock":
        return MockBenchmarkProvider()
    if name == "claude":
        return ClaudeAgentSDKProvider(**kwargs)
    raise ValueError(f"Unknown provider {name!r}.")


__all__ = [
    "BenchmarkProvider",
    "ClaudeAgentSDKProvider",
    "MockBenchmarkProvider",
    "ProviderRunResponse",
    "get_provider",
]
