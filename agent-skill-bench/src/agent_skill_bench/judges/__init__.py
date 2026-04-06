"""Judge registry for benchmark evaluation."""

from .base import BenchmarkJudge, JudgeDimensionScore, JudgeEvaluation
from .mock import MockBenchmarkJudge


def get_judge(name: str, **kwargs: object) -> BenchmarkJudge:
    """Return a built-in benchmark judge by name."""

    if kwargs:
        raise ValueError(f"Judge {name!r} does not accept options: {sorted(kwargs)}")
    if name == "mock":
        return MockBenchmarkJudge()
    raise ValueError(f"Unknown judge {name!r}.")


__all__ = [
    "BenchmarkJudge",
    "JudgeDimensionScore",
    "JudgeEvaluation",
    "MockBenchmarkJudge",
    "get_judge",
]
