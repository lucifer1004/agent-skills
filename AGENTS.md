# Agent Skills Repository Guide

## What This Repository Is

This repository is the unified maintenance workspace for the repository owner's published agent skills.

Top-level project directories typically correspond to published or publishable skill repositories.
The `.agents/skills/` subtree is reserved for internal repository-maintenance skills, such as authoring standards or review helpers.

Do not assume the repository is a single buildable application. Treat it as a workspace of reusable agent-skill assets.

## Working Model

- The repository root is for collection-level documentation and light coordination only.
- The root repository may also contain shared infrastructure that belongs to the collection itself, such as benchmark tooling.
- The root repository owns the shared Pixi workspace and repository-level task entrypoints.
- Child packages may keep package-level Pixi manifests when they are used as members of the root Pixi workspace, but workspace ownership stays at the root.
- Published skill repositories live as separate project directories.
- Internal repo-maintenance skills live under `.agents/skills/`.
- Prefer making changes inside the specific published skill project you are working on.
- Keep cross-project edits minimal unless the task is explicitly about repo-wide organization.

## Publication Boundary

- Treat `agent-skill-bench` and similar collection-wide tooling as root-repository code.
- Treat published-skill directories as future standalone repositories.
- If a published skill has not yet been published to its own remote repository, do not commit it into the root repository by default.
- Unpublished skill directories may exist locally in the workspace while remaining outside the root repository history.
- Once a published skill has its own remote repository, prefer reintroducing it to the root workspace as a submodule rather than folding its contents into the root history.

## Top-Level Expectations

- Add new published skills as separate project directories.
- Use `.agents/skills/<skill-name>/` only for internal maintenance skills that help manage this repository.
- Keep published skill project structure intact unless there is a clear maintenance reason to change it.
- If a published skill project has its own agent instructions such as `AGENTS.md`, `CLAUDE.md`, or equivalent, follow the nearest one in that subtree.
- Put shared repository notes in the root `AGENTS.md`; put project-specific instructions in the relevant project directory.

## Editing Rules

- Do not refactor unrelated skill directories while working on one skill.
- Avoid renaming published skill project directories or internal `.agents/skills/<skill-name>/` directories unless the task explicitly requires it.
- Preserve vendored or mirrored upstream files where possible.
- Document local-only changes clearly in the relevant project when they diverge from upstream behavior.
- Before editing or committing, classify each touched path as one of:
  - root-repository infrastructure
  - internal maintenance skill
  - published skill
- Do not mix those categories in one commit unless the task is explicitly about their shared boundary.

## Evidence Standard

- Do not claim a provider, CLI, or skill behavior is confirmed until you have direct evidence from code, logs, or raw output.
- Distinguish clearly between:
  - raw events or logs
  - normalized bench output
  - inferred conclusions
- If a result could be explained either by model behavior or by the bench harness, inspect the raw provider output before concluding which one is at fault.
- When provider message streams expose both intermediate messages and a final result, define and document which source is canonical instead of merging them ad hoc.

## Commit Discipline

- Before staging, explicitly verify which directories should be included and which must remain local-only.
- Check for transient artifacts before every commit, especially:
  - `.pixi/`
  - `.pytest_cache/`
  - `__pycache__/`
  - `.omc/`
  - benchmark run artifacts
- If the repository is being initialized or reorganized, verify the intended repository boundary before making the first commit.
- Do not place root-owned workspace tooling under a child package directory when that tooling is meant to serve the collection repository as a whole.
- It is acceptable for a child package to keep a package-only `pixi.toml` for `pixi-build`, as long as the actual workspace entrypoint remains at the repository root.

## Adding a New Skill

1. Create a new published skill project directory with a clear, stable name.
2. Keep the bundled skill content under a dedicated subtree such as `skills/<skill-name>/`.
3. Add project-level support files such as tests, tools, CI, and human-facing docs only when they materially help maintain the published skill.
4. Use `.agents/skills/` only when creating internal maintenance skills for this repository.
5. Update root-level documentation only if the collection structure changes.

## Navigation Rule

When working in this repository, first determine whether the target is a published skill project or an internal maintenance skill under `.agents/skills/`, then read the closest local instructions before editing files.
