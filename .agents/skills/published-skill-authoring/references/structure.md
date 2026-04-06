# Structure Standards

Use this file when deciding how a published skill repository should be laid out.

## Published Skill Repository

Use this when the skill is distributed as its own repo, package, or installable upstream project.

Typical split:

- repo root for maintenance, testing, CI, and human-facing docs
- bundled skill subtree such as `skills/<skill-name>/` for agent-consumed content

Common repo-level files:

- `README.md`
- `AGENTS.md` or `CLAUDE.md`
- `tests/`
- `tools/`
- CI or package manager files

Common bundled files:

- `SKILL.md`
- reference docs or sibling `*.md`
- `scripts/`
- `data/`
- `examples/` or `assets/`

## Directory Rules

- Keep bundled skill content under a clear subtree such as `skills/<skill-name>/`.
- Use a short hyphen-case name.
- Keep bundled skill content self-contained; avoid scattering agent-consumed files across the repo.
- Do not create deep reference trees. Prefer one level under `references/` or a small set of sibling docs.

## Routing Rule

`SKILL.md` must make the rest of the skill discoverable.

Every time you add one of these, register it in `SKILL.md` with a clear "when to use" pointer:

- a new reference file
- a new script
- a new asset that affects workflow
- a new data source or examples directory used by the bundled skill
- a new validation step that changes how the skill should be used

If a file is not reachable from `SKILL.md`, treat it as dead weight.

## When to Add Scripts

Add a script only when one of these is true:

- the same logic would otherwise be rewritten repeatedly
- output must be deterministic
- a workflow is too fragile to leave as free-form instructions

Otherwise prefer short, direct guidance in markdown.

## When to Add Assets

Add assets only when the skill needs files that become part of user output, such as:

- starter templates
- boilerplate source files
- icons or images used by generated output

Do not use `assets/` as a general dumping ground.

## Boundary Rule

Keep this boundary explicit:

- bundled skill files teach or assist the agent at runtime
- repo-level files help maintainers test, package, document, or refresh the bundled skill

Do not force bundled `SKILL.md` to describe every repo-maintenance detail. Link outward only when the agent truly needs that information to do the task.
