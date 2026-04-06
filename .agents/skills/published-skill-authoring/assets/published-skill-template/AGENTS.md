# Repository Guide

This repository maintains a published agent skill.

The bundled runtime-facing skill lives under `skills/your-skill/`.
Project-level files support testing, packaging, documentation, and release work.

When editing this repository:

- read `skills/your-skill/SKILL.md` first for runtime behavior
- keep repo-level maintenance guidance separate from bundled skill guidance
- avoid adding files to the bundled subtree unless they help the agent at runtime
