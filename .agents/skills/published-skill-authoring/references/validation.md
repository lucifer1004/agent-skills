# Validation Standards

Use this file when checking whether a published skill repository is ready to keep.

## Acceptance Checklist

- The bundled skill has a clear home such as `skills/<skill-name>/`.
- The bundled skill directory name is lowercase hyphen-case.
- `SKILL.md` exists and is the clear entry point.
- The frontmatter `name` matches the bundled skill name.
- The frontmatter `description` makes invocation conditions obvious.
- Canonical metadata lives in `SKILL.md` frontmatter unless there is a clear platform-specific reason not to.
- Every important bundled optional file is discoverable from `SKILL.md`.
- `agents/openai.yaml`, if present, matches the skill's actual role.
- Repo-level docs and bundled skill docs are not mixed together accidentally.
- If Gemini packaging is present, it wraps the same bundled skill instead of redefining it.

## Review Checks

Look for these common failures:

- dead references not linked from `SKILL.md`
- stale UI metadata after the skill scope changed
- reference files that should have stayed inside `SKILL.md`
- long instructions that should have been split into `references/`
- optional directories created without clear value
- repo-only maintenance steps leaking into bundled runtime guidance
- client-specific metadata pushed into the canonical layer without need
- Codex or Gemini packaging metadata treated as the canonical skill definition

## Update Rule

When editing an existing skill, verify both sides:

- the changed file itself is correct
- the navigation from `SKILL.md` still points to it accurately

For published repos, also verify that repo-level guidance still matches the bundled layout.

## Quality Bar

A good skill is:

- easy to trigger
- easy to navigate
- small at the entry point
- specific where workflows are fragile
- sparse where the model can already infer the rest
- explicit about which parts are canonical and which parts are adapters
