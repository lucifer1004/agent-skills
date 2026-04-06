# Agent Skills Repository Guide

## What This Repository Is

This repository is the unified maintenance workspace for the repository owner's published agent skills.

Top-level project directories typically correspond to published or publishable skill repositories.
The `.agents/skills/` subtree is reserved for internal repository-maintenance skills, such as authoring standards or review helpers.

Do not assume the repository is a single buildable application. Treat it as a workspace of reusable agent-skill assets.

## Working Model

- The repository root is for collection-level documentation and light coordination only.
- Published skill repositories live as separate project directories.
- Internal repo-maintenance skills live under `.agents/skills/`.
- Prefer making changes inside the specific published skill project you are working on.
- Keep cross-project edits minimal unless the task is explicitly about repo-wide organization.

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

## Adding a New Skill

1. Create a new published skill project directory with a clear, stable name.
2. Keep the bundled skill content under a dedicated subtree such as `skills/<skill-name>/`.
3. Add project-level support files such as tests, tools, CI, and human-facing docs only when they materially help maintain the published skill.
4. Use `.agents/skills/` only when creating internal maintenance skills for this repository.
5. Update root-level documentation only if the collection structure changes.

## Navigation Rule

When working in this repository, first determine whether the target is a published skill project or an internal maintenance skill under `.agents/skills/`, then read the closest local instructions before editing files.
