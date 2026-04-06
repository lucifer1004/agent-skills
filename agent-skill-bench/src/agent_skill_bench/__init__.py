"""Shared benchmarking infrastructure for agent skills."""

from .discovery import discover_case_files
from .evaluation import BenchmarkEvaluation, EvaluationCheck, evaluate_output
from .fixtures import (
    BUILTIN_EXECUTION_PROFILES,
    BenchmarkCase,
    BenchmarkEvaluationProfile,
    BenchmarkEvaluationRule,
    BenchmarkExpectations,
    BenchmarkKind,
    BenchmarkMode,
    BenchmarkPromptContract,
    BenchmarkSuite,
    EvaluationRuleKind,
    ExecutionProfile,
    ResolvedBenchmarkCase,
    get_execution_profile,
    load_case,
    load_suite,
    load_suite_for_case,
    resolve_case,
)
from .reporting import load_run_artifacts, summarize_run_artifacts
from .judges import (
    BenchmarkJudge,
    CodexCLIJudge,
    JudgeDimensionScore,
    JudgeEvaluation,
    MockBenchmarkJudge,
    get_judge,
)
from .runners import BenchmarkRunConfig, BenchmarkRunResult, BenchmarkRunner, SkillBindingSummary

__all__ = [
    "__version__",
    "BUILTIN_EXECUTION_PROFILES",
    "BenchmarkEvaluation",
    "BenchmarkJudge",
    "BenchmarkCase",
    "BenchmarkEvaluationProfile",
    "BenchmarkEvaluationRule",
    "BenchmarkExpectations",
    "BenchmarkKind",
    "BenchmarkMode",
    "BenchmarkPromptContract",
    "BenchmarkRunConfig",
    "BenchmarkRunResult",
    "BenchmarkRunner",
    "BenchmarkSuite",
    "ExecutionProfile",
    "EvaluationCheck",
    "CodexCLIJudge",
    "get_judge",
    "ResolvedBenchmarkCase",
    "JudgeDimensionScore",
    "JudgeEvaluation",
    "SkillBindingSummary",
    "MockBenchmarkJudge",
    "discover_case_files",
    "evaluate_output",
    "EvaluationRuleKind",
    "get_execution_profile",
    "load_case",
    "load_run_artifacts",
    "load_suite",
    "load_suite_for_case",
    "resolve_case",
    "summarize_run_artifacts",
]

__version__ = "0.1.0"
