---
name: self-curate
description: Record what this session learned in the vault's memory zones, flag stale docs, and file proposed factory changes as suggestions. Trigger on "wrap up", "save this", "remember this", "update the decision log/open questions"; after a decision settles or a correction worth keeping; or when the curate journal reaches the threshold in AGENTS.md (Self-curation).
user-invocable: true
disable-model-invocation: false
---

# self-curate

`$V` as defined in AGENTS.md. This lane writes memory and reads documentation; it edits no factory file. `.claude/skills/`, `.claude/agents/`, `.claude/rules/`, `AGENTS.md` and `REVIEW.md` are written only through a wave (decision log, 2026-08-24, D5; the deciding step is `curate-fold`). Because the lane touches no factory file, it can never block a wave merge.

## Procedure

1. Read: `.claude/.curate/journal.jsonl` (record how many lines were read: `N=$(wc -l < .claude/.curate/journal.jsonl)`), `.claude/.curate/last_curate.txt` (keep its value as `START_STAMP`), `git status --porcelain` and `git diff --stat`, today's `$V/90-meta/session-log/YYYY-MM-DD.md`, `head -40` of `$V/90-meta/decision-log.md` and `$V/90-meta/open-questions.md`, `$V/Home.md`. Then pick the lane type:
   - Hook-spawned (the invocation carries `triggered by:`; no user turns of its own): every journal entry newer than `START_STAMP` is work to record, whatever its `session:`. The journal holds counters only, so read the triggering transcript at `~/.claude/projects/<project-slug>/<session-id>.jsonl` from that timestamp on.
   - In-session (`/self-curate` typed in a working session): only entries whose `session:` is this session count; the id is in the path of any persisted tool result (`…/projects/<slug>/<session-id>/tool-results/…`). Foreign entries are context.
   Done: lane type stated; or "Nothing to curate." when the slice is empty and the tree is clean, and stop.
2. Route each item to exactly one zone. Formats are in each file's own header; do not restate them.
   - Session log `$V/90-meta/session-log/YYYY-MM-DD.md`: progress, what was tried, what was read. Create the file when missing, else append.
   - Decision log `$V/90-meta/decision-log.md`: a question settled with its why. Prepend (newest first), name what it supersedes, leave the old entry as it is; one breadcrumb line in the session log.
   - Open questions `$V/90-meta/open-questions.md`: a genuine fork as a `- [ ]` bullet with options and a decision trigger. An answered one moves: decision log first, then tick the bullet with a pointer to the decision date.
   - Cross-project memory: a durable, non-secret fact visible from other repos, written with the tool named in AGENTS.md (Self-curation). Batch the proposals and ask the owner once; nothing is written without that confirmation.
   - Handoff: at a session boundary the `handoff` skill writes `$V/90-meta/handoffs/`; this lane only points at the newest file from the session log.
   - Inbox residue: a `$V/00-inbox/` dump now merged into its note is deleted (working agreement in `$V/Home.md`).
   - Discard: one-off detail, speculation, already recorded.
   The provenance boundary in AGENTS.md applies to every zone: no employer or client names, internal hostnames, credentials or verbatim private code, in any file.
   Done: every item has one zone or is discarded.
3. Documentation coverage: read `.claude/skills/INDEX.md`, every `MODULE.md`, the build repo's `docs/` tree (layout in `$V/docs/architecture/system-structure.md`) and the indexes under `$V/docs/` against the current tree and the diff since `START_STAMP`. An entry naming a file, section or behaviour that no longer exists, or missing one that does, is stale. Write the list under `Docs stale:` in the session log as `path — what is wrong`, or `Docs stale: none`; this lane rewrites none of them. Done: the line is in the session log.
4. Suggestions: any learning that would change a skill, agent, rule, `AGENTS.md` or `REVIEW.md` becomes one entry in `$V/90-meta/suggestions.md`, in the shape its header gives, decision field left empty. Triggers: an owner correction or explicit approval of a non-obvious approach; a rule stated outright ("from now on", "always", "never"); the same recovery sequence repeated after one class of failure; a workflow re-derived from scratch; a skill never fired; an INDEX line over the description budget in `.claude/rules/agent-files.md`. When an earlier entry covers the same item, cite it, so recurrence is visible to `curate-fold`. This review runs every curate. Done: each item is one entry, or the report says `suggestions: none`.
5. Apply: `Edit` over `Write`; YAML front-matter intact; wiki-links vault-internal (`[[90-meta/decision-log]]`) and resolving. Nothing is deleted from the decision log, open questions, `$V/10-executive/` or `$V/docs/`: append, edit in place or move, and mark superseded text as superseded. No secret, token or `.env` value goes anywhere. Done: `git -C <build repo> status --porcelain` shows no factory file changed.
6. Decision-log budget: `wc -l $V/90-meta/decision-log.md` over 400 lines means compaction. Move the oldest fifth (bottom of the file; keep tightly related entries together) verbatim to `$V/90-meta/archive/decision-log-<YYYY-MM>.md` and replace the block with `- (archived: <one-line summary>) → [[90-meta/archive/decision-log-<YYYY-MM>]]`. Repeat up to three rounds; still over, stop and say so in the report. Delete files in `.claude/.curate/archive/` older than 30 days. Done: the count is under 400 or the warning is in the report.
7. Rotate and re-stamp. Only the `N` lines read in step 1 are processed; lines appended since stay live (neither hook rotates, this step does):
   ```
   J=.claude/.curate/journal.jsonl; mkdir -p .claude/.curate/archive
   head -n "$N" "$J" > ".claude/.curate/archive/journal-$(date -u +%Y%m%dT%H%M%SZ).jsonl" && tail -n +$((N+1)) "$J" > "$J.tmp" && mv "$J.tmp" "$J"
   date -u +"%Y-%m-%dT%H:%M:%SZ" > .claude/.curate/last_curate.txt
   ```
   The journal and the stamp are shared by every session on this checkout, worktrees included. Re-read the stamp: older than `START_STAMP` means a sibling curate raced this one; stamp again with the current time and note the race in the session log. Done: the stamp is newer than `START_STAMP`.

## Output

```
Curated N turns since <START_STAMP> (<lane type>).
- session-log/YYYY-MM-DD.md: <one-line change>
- decision-log.md: <N added / no change> (<N> lines, cap 400[, compacted M entries])
- open-questions.md: <N opened / N resolved / no change>
- cross-project memory: <N confirmed and written / not used>
- docs stale: <N flagged / none>
- suggestions.md: <N entries / none>
- 00-inbox: <N merged and deleted / no change>
- discarded: <N>
```

## Limits

The lane records and flags; it decides nothing about the factory, so a suggestion waits until `curate-fold` runs. The journal shows that a turn edited or tested something, never what it learned; the transcript read in step 1 is the only source for that, and a transcript already rotated out is lost to this lane. Single-turn lookups and planning that settled nothing produce no journal entry and need no run.
