"""Benchmark suite and case discovery helpers."""

from __future__ import annotations

from pathlib import Path


DEFAULT_CASE_GLOB = "*/benchmarks/cases/*.json"


def discover_case_files(root: str | Path, relative_glob: str = DEFAULT_CASE_GLOB) -> list[Path]:
    """Discover benchmark case files below a collection root."""

    root_path = Path(root)
    return sorted(path for path in root_path.glob(relative_glob) if path.is_file())
