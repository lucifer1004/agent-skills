"""Shared benchmarking infrastructure for agent skills."""

from .discovery import discover_case_files
from .fixtures import (
    BUILTIN_EXECUTION_PROFILES,
    BenchmarkCase,
    BenchmarkExpectations,
    BenchmarkKind,
    BenchmarkMode,
    BenchmarkPromptContract,
    BenchmarkSuite,
    ExecutionProfile,
    ResolvedBenchmarkCase,
    get_execution_profile,
    load_case,
    load_suite,
    load_suite_for_case,
    resolve_case,
)
from .runners import BenchmarkRunConfig, BenchmarkRunResult, BenchmarkRunner, SkillBindingSummary

__all__ = [
    "__version__",
    "BUILTIN_EXECUTION_PROFILES",
    "BenchmarkCase",
    "BenchmarkExpectations",
    "BenchmarkKind",
    "BenchmarkMode",
    "BenchmarkPromptContract",
    "BenchmarkRunConfig",
    "BenchmarkRunResult",
    "BenchmarkRunner",
    "BenchmarkSuite",
    "ExecutionProfile",
    "ResolvedBenchmarkCase",
    "SkillBindingSummary",
    "discover_case_files",
    "get_execution_profile",
    "load_case",
    "load_suite",
    "load_suite_for_case",
    "resolve_case",
]

__version__ = "0.1.0"
