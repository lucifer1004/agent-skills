---
name: published-skill-authoring
description: Use when creating, restructuring, editing, reviewing, or validating published agent skill repositories with bundled skill content, maintenance tooling, tests, and distribution metadata.
---

# Published Skill Authoring

Create and maintain published agent skill repositories.

This skill is for published skills, not generic local-only skills.

## Default Shape

```text
repo-root/
├── README.md
├── AGENTS.md or CLAUDE.md
├── tests/
├── tools/
└── skills/<skill-name>/
    ├── SKILL.md
    ├── references or *.md
    ├── scripts/
    ├── data/
    └── examples/ or assets/
```

`SKILL.md` is always the entry point for the bundled skill. Surrounding repo files support maintenance, testing, packaging, and distribution.

## Workflow

1. Identify whether the task is creating a new published skill repo, updating one, or reviewing one.
2. Read the bundled `SKILL.md` first, then the smallest relevant bundled reference files.
3. Keep `SKILL.md` focused on trigger conditions, workflow, and routing.
4. Treat the Agent Skills spec as the canonical skill format.
5. Keep the bundled skill portable across Codex, Claude Code, and Gemini CLI.
6. Move detailed standards, examples, or long guidance into bundled reference files or sibling docs.
7. Keep repo-level maintenance guidance separate from bundled runtime guidance.
8. Add scripts, examples, or data only when they materially improve reliability or discoverability.
9. Validate both the bundled skill surface and the repo-level maintenance surface.

## Core Rules

- Use lowercase hyphen-case names for skill directories.
- Keep one bundled entry point: `SKILL.md`.
- Every important bundled reference file must be linked directly from `SKILL.md`.
- Distinguish bundled skill content from repo-only maintenance content.
- Prefer a canonical open-skill core plus thin platform adapters.
- Prefer progressive disclosure over one large instruction file.
- Lead with action and routing, not background.
- Keep examples minimal and task-shaped.
- If bundled `agents/openai.yaml` exists, keep it aligned with the skill's actual scope.
- In published repos, keep human-facing repo docs outside the bundled skill subtree.

## Read These References When Needed

- For published-repo layout, routing, and file-boundary decisions, read [references/structure.md](references/structure.md).
- For SKILL-platform compatibility and metadata boundaries across Codex, Claude Code, and Gemini CLI, read [references/compatibility.md](references/compatibility.md).
- For acceptance criteria and review checks, read [references/validation.md](references/validation.md).

## Template

Start from [assets/published-skill-template](assets/published-skill-template) when creating a new published skill repo.

## Done Criteria

A skill is in good shape when:

- its name and description make invocation obvious
- `SKILL.md` gives a clear path to the right details
- references are shallow and directly discoverable
- optional files exist only when they pull real weight
- compatibility choices are explicit instead of mixed together ad hoc
- repo-only files do not leak into bundled skill instructions by accident
- validation finds no dead routes or stale metadata
