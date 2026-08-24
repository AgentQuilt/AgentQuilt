---
name: skill-author
description: Write or change a project skill in the house shape: budgets, shadowing check, staged draft, test, INDEX entry. Use whenever a skill is created or its frontmatter changes.
---

# skill-author

Rules for the text are in `.claude/rules/agent-files.md`; this is the procedure around them.

## Procedure

1. Reuse before create: name the closest existing skill (`.claude/skills/INDEX.md`) and why a subsection there does not cover the need. Done: one sentence in the change description.
2. Shadowing check: `ls ~/.claude/skills/` must not list the name; a project skill loses to a user-level one. Done: the command output is in the change description.
3. Frontmatter: `name`; `description` = what it does plus when to reach for it, third person, at most 30 words, 1,536 characters is the hard limit the loader applies; `disable-model-invocation: true` when only Fable or the owner fire it. Detail belongs in the body, which loads only on invocation. Done: `wc -w` on the description.
4. Body: procedure with a done-condition per step, an output contract, and a "Limits (be honest)" section stating what the skill cannot check. Cap 110 lines (or the lower cap in the factory plan); detail in `references/`, one level deep. Done: `wc -l`.
5. Stage as `.claude/skills/<name>-draft/`, run it once on a real input, then rename atomically (`git mv`) to the final name. Done: the draft directory is gone.
6. Scripts under `scripts/`: `set -euo pipefail`, a usage comment, `bash -n` clean, one smoke run recorded in the change description. Done: exit codes match the comment.
7. Add one line to `.claude/skills/INDEX.md` (alphabetical; format in `self-curate`, Step 3) and, when a Claude Code session is open, restart it and confirm the skill is listed. Done: INDEX line present.

## Limits (be honest)

The procedure checks shape, not usefulness; a skill that is never fired is found by `self-curate`'s learnings review, not here. The shadowing check covers `~/.claude/skills/` only; plugin skills need `claude plugin` inspection.
