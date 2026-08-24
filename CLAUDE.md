# CLAUDE.md

**[`AGENTS.md`](AGENTS.md) is the canonical agent guide for this repo — read it
first.** It covers the product, the vault next door, the working agreement,
architecture reading, model routing, the sub-agent roster, the self-curation
system, memory conventions, and the provenance boundary. This file is only a
pointer plus the Claude-Code-specific wiring below. **Where the two disagree,
AGENTS.md wins.**

## Claude Code wiring

- **Hooks** live in `.claude/settings.json`: `Stop` → `post-turn-journal.py`,
  `SessionEnd` / `PreCompact` → `run-curate.sh`. Behaviour and thresholds are
  described in AGENTS.md ("Self-curation system"); logs land in `.claude/.curate/logs/`.
- **Skills** are catalogued in `.claude/skills/INDEX.md`; any new skill must be added there.
- **Permissions** in `settings.json` start empty and grow only from this project's own use.
  `settings.local.json` (not for the public repo) grants read access to the sibling vault via `additionalDirectories`.
