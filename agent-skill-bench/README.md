# agent-skill-bench

`agent-skill-bench` is a Python package for benchmarking published agent skills.

It is intended to live in the root `agent-skills` collection repository and provide shared infrastructure for:

- benchmark suite and case loading
- provider runner adapters
- scoring and regression comparison
- benchmark discovery across skill projects

This initial scaffold sets up the package as a Pixi-built Python project so the framework can evolve behind a stable package boundary.

## Model

The framework is organized around four distinct concepts:

- `suite.json`: suite-level defaults such as the default skill, execution profile, and evaluation profile
- case files under `benchmarks/cases/`: task, context, and expectations
- suite-level benchmark prompt contracts: shared run instructions and mode-specific output headings
- execution profiles: stable run policies such as `isolated_prompt` and `isolated_repo_copy`
- run artifacts: saved provider outputs and metadata for each benchmark execution

For prompt design, the framework now separates:

- the case's `prompt`, which should read like a real user request
- the suite's `benchmark_prompt`, which adds stable benchmarking rules and required output headings

This keeps cases realistic while still producing outputs that are comparable across runs.

## CLI Behavior

`agent-skill-bench run` always does both:

- prints JSON results to stdout for piping and scripting
- saves the same results to a JSON artifact file on disk

By default, result files are written to:

- `<root>/.agent-skill-bench/runs/` when `--root` is used
- `<cwd>/.agent-skill-bench/runs/` when explicit `--case` paths are used

Use `--output` to choose an exact file path or `--results-dir` to override the default artifact directory.

Benchmark runs can also inject explicit skills instead of inheriting whatever is installed in the user's Claude environment:

- add `skill_paths` to a case JSON
- or pass one or more `--skill /path/to/skill-or-SKILL.md` flags at runtime

For Claude runs, injected skills are copied into the isolated local skill directory under the benchmark working directory, so only explicitly declared skills participate in the run.

Each saved run artifact now distinguishes three different states:

- `requested_skills`: what the suite or CLI asked the run to bind
- `injected_skills`: what the provider actually materialized into the isolated Claude project
- `registered_skills`: what the Claude CLI reported as available in its `system/init` event

This is intentional. "Injected" and "registered in the Claude session" are not the same thing, and neither one by itself proves behavioral use in the final answer. The normalized `skill_binding` block in each run artifact makes that distinction explicit.

## Layout

- `src/agent_skill_bench/` contains the package code
- `tests/` contains package-level tests
- `pixi.toml` defines the Pixi workspace and package-build configuration
