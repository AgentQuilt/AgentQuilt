---
name: curate-fold
description: Decides each open suggestions-file entry, drains the curator's inbox into the memory zones, and routes accepted factory changes into a wave. Fable fires it at the start of every wave.
---

# curate-fold

`$V` as defined in AGENTS.md. The file is `$V/90-meta/suggestions.md`, written by `self-curate` (decision log, 2026-08-24, D5). Fires at the start of every wave, and whenever `grep -c '→ \*open\*$'` over that file and `$V/90-meta/curate-inbox.md` together reaches five (each file's header carries one example marker; subtract it).

## Procedure

1. Read the file. An entry with an empty decision field is open. Done: the open count is stated, `0` included.
2. For each open entry, decide in one sentence: accept when the change follows from the evidence and the target file is the rule's one home; reject when the evidence is one session, one error string or a rule already stated elsewhere; defer when it needs information the entry lacks, naming what. Cited earlier entries on the same item weigh in favour of accepting. Done: every open entry has a sentence.
3. Route accepted entries. One line of change (a cap number, a name, a by-name reference): the orchestrator folds it directly into the running wave's branch, or, with no wave running, into the next wave's first commit; either way it is named in that wave's context file, so Codex sees it. Anything larger: a task line for the running or next wave; past a line's worth of design, a task in the plan through `plan-gate`. The change itself lands through the wave loop; this skill edits no factory file. Done: every accepted entry names the fold, wave or plan that carries it.
4. Mark each decided entry in place, `→ *<decision> (YYYY-MM-DD): <sentence>*`, and delete nothing. Done: no open entry from step 1 remains.
5. Drain `$V/90-meta/curate-inbox.md` (written by the hook-spawned `self-curate` lane, decision log 2026-08-26): write each open entry to its named zone, edited as needed under the zone conventions in `self-curate`, or discard it, and mark it in place `→ *promoted (YYYY-MM-DD): <zone>*` or `→ *discarded (YYYY-MM-DD): <sentence>*`; delete nothing. Done: no open inbox entry remains.

## Output

One line per decided entry, `<date> — <target file> — <decision> — <where it goes>`, then the deferred count (deferred entries are decided and marked; they reopen when the named information arrives).

## Limits

The decision is Fable's judgment on the entry's evidence; a suggestion whose source transcript has rotated out cannot be re-checked and is decided on the entry alone. Nothing here verifies that a routed task was built; the wave's verifier does.
