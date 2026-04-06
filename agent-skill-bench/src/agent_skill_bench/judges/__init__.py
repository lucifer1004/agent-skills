"""Judge registry for benchmark evaluation."""

from .base import BenchmarkJudge, JudgeDimensionScore, JudgeEvaluation
from .codex import CodexCLIJudge
from .mock import MockBenchmarkJudge


def get_judge(name: str, **kwargs: object) -> BenchmarkJudge:
    """Return a built-in benchmark judge by name."""

    normalized_kwargs = {key: value for key, value in kwargs.items() if value is not None}
    if name == "mock":
        if normalized_kwargs:
            raise ValueError(f"Judge {name!r} does not accept options: {sorted(normalized_kwargs)}")
        return MockBenchmarkJudge()
    if name == "codex":
        return CodexCLIJudge(**normalized_kwargs)
    raise ValueError(f"Unknown judge {name!r}.")


__all__ = [
    "BenchmarkJudge",
    "CodexCLIJudge",
    "JudgeDimensionScore",
    "JudgeEvaluation",
    "MockBenchmarkJudge",
    "get_judge",
]
