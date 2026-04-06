# Repository Guide

This repository subtree maintains the `agent-skill-bench` Python package.

The package provides shared benchmarking infrastructure for published agent skills in the root collection repository.

When editing this project:

- keep package code under `src/agent_skill_bench/`
- keep project-level maintenance files at the repo root of this subtree
- keep package metadata such as `pyproject.toml` in this subtree
- keep the package-only `pixi.toml` in this subtree for `pixi-build`, but keep the collection workspace `pixi.toml` at the repository root
- treat skill-specific benchmark suites as external inputs, not built-in package data by default
- prefer stable schemas and provider interfaces over ad hoc runner logic
