# Compatibility Strategy

Read this file when designing a published skill that should work across Codex, Claude Code, and Gemini CLI.

## Default Position

Treat the open Agent Skills format as the canonical source:

- `SKILL.md`
- `scripts/`
- `references/`
- `assets/`

Then add thin platform-specific layers only where a client needs extra metadata or packaging:

- Codex
- Claude Code
- Gemini CLI

Keep one canonical bundled skill and adapt only the metadata or release packaging around it.

## Platform Differences

### Codex

Codex supports the standard skill layout and adds optional `agents/openai.yaml`.

Use Codex-specific metadata for:

- UI labels
- icons and brand color
- default prompt
- implicit-invocation policy
- tool dependency declarations

Keep this file as a Codex overlay, not as the source of truth for the skill itself.

### Claude Code

Claude Code closely follows the open skill format and relies more heavily on `SKILL.md` frontmatter.

Notable frontmatter support includes:

- `license`
- `allowed-tools`
- `metadata`

Prefer putting published-skill metadata that should stay portable into frontmatter fields supported by the open spec or by Claude's implementation.

### Gemini CLI

Gemini CLI supports bundled agent skills, usually inside an extension that carries its own manifest.

Treat the skill directory as canonical content and the extension manifest as packaging metadata.

Do not move core workflow semantics out of `SKILL.md` just because Gemini packaging adds another manifest layer.

## Canonical Metadata Policy

Put cross-client skill metadata in `SKILL.md` frontmatter when possible:

- `name`
- `description`
- `license`
- `compatibility`
- `metadata`
- `allowed-tools`

Do not invent vendor-specific frontmatter keys unless the target client requires them and the repo is explicitly choosing to specialize.

## Portable Baseline

Prefer this layering:

1. Canonical bundled skill for all SKILL-native clients
2. Codex overlay in `agents/openai.yaml`
3. Gemini packaging manifest when releasing as an extension

This keeps the published skill portable while still allowing each client to expose its own UX and packaging model.

## Review Questions

When reviewing compatibility, ask:

- Is `SKILL.md` still the real source of truth?
- Did platform-specific metadata stay in the platform-specific layer?
- Can Codex, Claude Code, and Gemini CLI all consume the same bundled core?
- Did any client-specific requirement leak into the canonical skill without a strong reason?
