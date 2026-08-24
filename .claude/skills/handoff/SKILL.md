---
name: handoff
description: Save a half-page session handoff to the vault, or resume from the latest one with a branch check. Fable or the owner fire it at a session boundary.
disable-model-invocation: true
---

# handoff

`V=../AgentQuilt-Vault`; handoffs live in `$V/90-meta/handoffs/`. Infer before asking: git state, the session log and the decision-log head answer most questions.

## Save

1. File `$V/90-meta/handoffs/YYYY-MM-DD-<topic>-handoff.md`, Obsidian front-matter (`tags: [meta, handoff]`, `date:`). Done: the file exists and is under half a page.
2. Sections: Branch (mandatory: `git branch --show-current`, worktree path, HEAD hash, dirty or clean); State (what is done, what is carried, by path); Verified (each claim with its evidence, tagged TESTED, PARTIAL or INFERRED); Next (exactly one runnable command that picks the work up); Skills to load next session, by name. Done: every section present; nothing quoted that a path can point at.
3. Line in today's session log pointing at the file. Done.

## Resume

1. Read the newest file in `$V/90-meta/handoffs/`, then run `git branch --show-current`. A mismatch with the recorded branch is a warning, and the choice is three-way: switch to the recorded branch, continue on the current one and say so in the log, or discard the handoff. Done: the choice is stated.
2. Run `catchup`, then the handoff's Next command. Done: output of the command reported.

## Limits

The Verified section is only as honest as its tags; an INFERRED line is a claim, not evidence. Nothing here writes to git.
