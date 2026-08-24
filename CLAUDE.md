# CLAUDE.md

**[`AGENTS.md`](AGENTS.md) is the canonical agent guide for this repo; where the
two disagree, AGENTS.md wins.** This file adds only the Claude Code wiring.

@AGENTS.md

## Claude Code wiring

- **Hooks** live in `.claude/settings.json`: `PreToolUse` on Bash → `git-guard.py` and
  `bash-guard.py`; `Stop` → `post-turn-journal.py`; `SessionEnd` / `PreCompact` → `run-curate.sh`.
  Logs land in `.claude/.curate/logs/`. Authoring rules: `.claude/rules/hooks.md`.
- **Skills** are catalogued in `.claude/skills/INDEX.md`; any new skill must be added there.
- **Permissions** in `settings.json` start empty and grow only from this project's own use.
  `settings.local.json` (not for the public repo) grants read access to the sibling vault via `additionalDirectories`.
