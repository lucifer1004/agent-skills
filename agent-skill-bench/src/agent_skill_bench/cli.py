"""CLI entry point for benchmark discovery and execution."""

from __future__ import annotations

import argparse
from datetime import UTC, datetime
import json
import logging
from pathlib import Path
import sys
from typing import Sequence

from .discovery import discover_case_files
from .providers import get_provider
from .reporting import load_run_artifacts, summarize_run_artifacts
from .runners import BenchmarkRunConfig, BenchmarkRunner, save_run_results

LOG_LEVELS = ("CRITICAL", "ERROR", "WARNING", "INFO", "DEBUG")


def main(argv: Sequence[str] | None = None) -> int:
    """Run the benchmark CLI."""

    parser = build_parser()
    args = parser.parse_args(argv)
    _configure_logging(args.log_level)

    if args.command == "discover":
        paths = discover_case_files(args.root)
        print(json.dumps([str(path) for path in paths], indent=2))
        return 0

    if args.command == "run":
        provider = get_provider(
            args.provider,
            cwd=args.cwd,
            system_prompt=args.system_prompt,
            max_turns=args.max_turns,
            timeout_seconds=args.timeout_seconds,
            cli_path=args.cli_path,
        )
        runner = BenchmarkRunner(provider)
        case_paths = _resolve_case_paths(args.root, args.case)
        config = BenchmarkRunConfig(
            provider_name=provider.name,
            suite_filter=args.suite,
            case_ids=set(args.case_id),
            execution_profile=args.execution_profile,
            skill_paths=[path.resolve() for path in args.skill] if args.skill else None,
            no_skills=args.no_skills,
        )
        results = runner.run_case_files(case_paths, config=config)
        output_path = _resolve_output_path(args)
        save_run_results(results, output_path)
        print(f"Saved benchmark results to {output_path}", file=sys.stderr)
        print(json.dumps([result.to_dict() for result in results], indent=2))
        return 0

    if args.command == "report":
        records = load_run_artifacts(args.run_artifact)
        print(json.dumps(summarize_run_artifacts(records), indent=2))
        return 0

    parser.error(f"Unknown command: {args.command}")
    return 2


def build_parser() -> argparse.ArgumentParser:
    """Build the CLI argument parser."""

    parser = argparse.ArgumentParser(prog="agent-skill-bench")
    parser.add_argument(
        "--log-level",
        default="WARNING",
        choices=LOG_LEVELS,
        help="Standard logging level",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    discover = subparsers.add_parser("discover", help="Discover benchmark case files")
    discover.add_argument("root", type=Path, help="Collection root to search")

    run = subparsers.add_parser("run", help="Run benchmark cases through a provider")
    run.add_argument("--provider", default="mock", help="Provider name")
    run.add_argument("--root", type=Path, help="Collection root to discover cases from")
    run.add_argument("--cwd", type=Path, help="Optional provider working directory override")
    run.add_argument("--system-prompt", help="Optional provider system prompt")
    run.add_argument(
        "--max-turns",
        type=int,
        help="Provider max turns override. Defaults to the selected execution profile.",
    )
    run.add_argument(
        "--timeout-seconds",
        type=float,
        help="Provider timeout override in seconds. Defaults to the selected execution profile.",
    )
    run.add_argument("--cli-path", help="Optional path to the Claude Code executable")
    run.add_argument(
        "--skill",
        action="append",
        default=[],
        type=Path,
        help="Explicit skill directory or SKILL.md path. Replaces suite-default skills for this run.",
    )
    run.add_argument(
        "--no-skills",
        action="store_true",
        help="Run without injecting any skills, even if the suite defines defaults.",
    )
    run.add_argument(
        "--execution-profile",
        help="Execution profile override. Defaults to the case or suite profile.",
    )
    run.add_argument(
        "--results-dir",
        type=Path,
        help="Directory for auto-saved result JSON files. Defaults to <root or cwd>/.agent-skill-bench/runs/",
    )
    run.add_argument(
        "--output",
        type=Path,
        help="Exact file path for the saved run results JSON.",
    )
    run.add_argument(
        "--case",
        action="append",
        default=[],
        type=Path,
        help="Explicit benchmark case file path. Can be passed multiple times.",
    )
    run.add_argument("--suite", help="Optional suite filter")
    run.add_argument(
        "--case-id",
        action="append",
        default=[],
        help="Optional case id filter. Can be passed multiple times.",
    )

    report = subparsers.add_parser("report", help="Summarize saved benchmark run artifacts")
    report.add_argument(
        "run_artifact",
        nargs="+",
        type=Path,
        help="Saved benchmark run JSON artifact(s) to summarize.",
    )

    return parser


def _resolve_case_paths(root: Path | None, cases: list[Path]) -> list[Path]:
    """Resolve case inputs from explicit files or a discovery root."""

    if cases:
        return cases
    if root is None:
        raise ValueError("Either --root or at least one --case must be provided.")
    return discover_case_files(root)


def _resolve_output_path(args: argparse.Namespace) -> Path:
    """Resolve the destination path for persisted run results."""

    if args.output is not None:
        return args.output

    results_dir = args.results_dir or _default_results_dir(args.root)
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
    return results_dir / f"{timestamp}-{args.provider}.json"


def _default_results_dir(root: Path | None) -> Path:
    """Return the default directory for auto-saved run artifacts."""

    base_dir = root if root is not None else Path.cwd()
    return base_dir / ".agent-skill-bench" / "runs"


def _configure_logging(level_name: str) -> None:
    """Configure standard library logging for the CLI."""

    logging.basicConfig(
        level=getattr(logging, level_name),
        format="%(levelname)s %(name)s: %(message)s",
    )
