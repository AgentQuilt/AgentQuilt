---
name: self-curate
description: Record what this session learned in the vault's memory zones, flag stale docs, and file proposed factory changes as suggestions. Trigger on "wrap up", "save this", "remember this", "update the decision log/open questions"; after a decision settles or a correction worth keeping; or when the curate journal reaches the threshold in AGENTS.md (Self-curation).
user-invocable: true
disable-model-invocation: false
---

# self-curate

`$V` as defined in AGENTS.md. This lane writes memory and reads documentation; it edits no factory file and commits nothing in the build repo (vault writes are the owner's to commit). Factory files are `.claude/skills/`, `.claude/agents/`, `.claude/rules/`, `.claude/hooks/`, `.claude/settings.json`, `AGENTS.md`, `REVIEW.md` and `CLAUDE.md`; they are written only through a wave (decision log, 2026-08-24, D5; the deciding step is `curate-fold`).

## Procedure

1. Read: `.claude/.curate/journal.jsonl` (snapshot what was read: `SNAP=$(mktemp); cp .claude/.curate/journal.jsonl "$SNAP"`), `.claude/.curate/last_curate.txt` (keep its value as `START_STAMP`), a checksum of the factory files (keep it: `FP() { git ls-files -z -- .claude/skills .claude/agents .claude/rules .claude/hooks .claude/settings.json AGENTS.md REVIEW.md CLAUDE.md | xargs -0 sha1sum; }; BEFORE=$(FP)`) and `git diff --stat`, today's `$V/90-meta/session-log/YYYY-MM-DD.md`, `head -40` of `$V/90-meta/decision-log.md` and `$V/90-meta/open-questions.md`, `$V/Home.md`. Then pick the lane type:
   - Hook-spawned (the invocation carries `triggered by:`; no user turns of its own): every live journal line is work to record, whatever its `session:` or age. The journal holds counters only, so read every transcript the selected entries name (the unique set of their `transcript` paths, under `~/.claude/projects/<project-slug>/`), each from the timestamp of its oldest live journal line on (never from the stamp); a transcript that cannot be read is named under `Unread:` in the session log and its entries are archived with the rest.
   - In-session (`/self-curate` typed in a working session): only entries whose `session:` is this session count; the id is in the path of any persisted tool result (`…/projects/<slug>/<session-id>/tool-results/…`). Foreign entries are context.
   Done: lane type stated; or "Nothing to curate." when the slice is empty and the tree is clean, and stop.
2. Route each item to exactly one zone. Formats are in each file's own header.
   - Session log `$V/90-meta/session-log/YYYY-MM-DD.md`: progress, what was tried, what was read. Create the file when missing, else append.
   - Decision log `$V/90-meta/decision-log.md`: a question settled with its why. Prepend (newest first), name what it supersedes, leave the old entry as it is; one breadcrumb line in the session log.
   - Open questions `$V/90-meta/open-questions.md`: a genuine fork as a `- [ ]` bullet with options and a decision trigger. An answered one moves: decision log first, then tick the bullet with a pointer to the decision date.
   - Cross-project memory: a durable, non-secret fact visible from other repos, written with the tool named in AGENTS.md (Self-curation). Batch the proposals and ask the owner once; nothing is written without that confirmation.
   - Handoff: at a session boundary the `handoff` skill writes `$V/90-meta/handoffs/`; this lane only points at the newest file from the session log.
   - Inbox residue: a `$V/00-inbox/` dump now merged into its note is deleted (working agreement in `$V/Home.md`).
   - Discard: one-off detail, speculation, already recorded.
   The provenance boundary in AGENTS.md applies to every zone.
   Done: every item has one zone or is discarded.
3. Documentation coverage: read `.claude/skills/INDEX.md`, every `MODULE.md`, the build repo's `docs/` tree when it exists, and `$V/docs/architecture/` against the current tree and the diff since `START_STAMP`. An entry naming a file, section or behaviour that no longer exists, or missing one that does, is stale. Write the list under `Docs stale:` in the session log as `path — what is wrong`, or `Docs stale: none`; this lane rewrites none of them. Done: the line is in the session log.
4. Suggestions: any learning that would change any factory file becomes one entry in `$V/90-meta/suggestions.md`, in the shape its header gives, decision field left empty. Triggers: an owner correction or explicit approval of a non-obvious approach; a rule stated outright ("from now on", "always", "never"); the same recovery sequence repeated after one class of failure; a workflow re-derived from scratch; a skill never fired; an INDEX line over the description budget in `.claude/rules/agent-files.md`. When an earlier entry covers the same item, cite it. This review runs every curate. Done: each item is one entry, or the report says `suggestions: none`.
5. Apply: `Edit` over `Write`; Obsidian conventions as AGENTS.md states them. Nothing is deleted from the decision log, open questions, `$V/10-executive/` or `$V/docs/`: append, edit in place or move, and mark superseded text as superseded. Done: `[ "$BEFORE" = "$(FP)" ]` holds.
6. Decision-log budget: `wc -l $V/90-meta/decision-log.md` over 400 lines means compaction. Move the oldest fifth (bottom of the file; keep tightly related entries together) verbatim to `$V/90-meta/archive/decision-log-<YYYY-MM>.md` and replace the block with `- (archived: <one-line summary>) → [[90-meta/archive/decision-log-<YYYY-MM>]]`. Repeat up to three rounds; still over, stop and say so in the report. Delete files in `.claude/.curate/archive/` older than 30 days. Done: the count is under 400 or the warning is in the report.
7. Rotate and re-stamp. Only the lines in the step-1 snapshot are processed; anything appended or rotated by a sibling since stays as it is. A hook-spawned lane archives every snapshot line; an in-session lane archives only its own session's lines among them (`SID` is this session's id from step 1). Lines are claimed by content with multiplicity, under the same `journal.lock` the hook appends under:
   ```
   J=.claude/.curate/journal.jsonl; mkdir -p .claude/.curate/archive; A=$(mktemp ".claude/.curate/archive/journal-$(date -u +%Y%m%dT%H%M%SZ)-XXXX.jsonl")
   grep -F "$SID" "$SNAP" > "$SNAP.mine"; flock .claude/.curate/journal.lock -c "awk 'NR==FNR{c[\$0]++;next} c[\$0]>0{c[\$0]--;print}' '$J' '$SNAP.mine' > '$A'; awk 'NR==FNR{c[\$0]++;next} c[\$0]>0{c[\$0]--;next} 1' '$A' '$J' > '$J.$$'; mv '$J.$$' '$J'"; rm -f "$SNAP" "$SNAP.mine"   # hook lane: SID="" (matches every line); each line is claimed once, so a duplicate appended later or already taken by a sibling is left alone
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

The journal shows that a turn edited or tested something, never what it learned; the transcript read in step 1 is the only source for that, and a transcript already rotated out is lost to this lane. Single-turn lookups and planning that settled nothing produce no journal entry and need no run.
