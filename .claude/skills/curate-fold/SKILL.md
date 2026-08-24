---
name: curate-fold
description: Decide each open entry in the vault's suggestions file (accept, reject, defer) and route accepted factory changes into a wave. Fable fires it at a phase boundary; the curate lane never does.
disable-model-invocation: true
---

# curate-fold

`$V` as defined in AGENTS.md. The file is `$V/90-meta/suggestions.md`; the curate lane appends there instead of editing any factory file (decision log, 2026-08-24, D5). Runs after a wave merges, or on `wrap up` before `handoff`.

## Procedure

1. Read the file. An entry with an empty decision field is open. Done: the open count is stated, `0` included.
2. For each open entry, decide in one sentence: accept when the change follows from the evidence and the target file is the rule's one home; reject when the evidence is one session, one error string or a rule already stated elsewhere; defer when it needs information the entry lacks, naming what. Cited earlier entries on the same item weigh in favour of accepting. Done: every open entry has a sentence.
3. Route accepted entries. One line of change: a task line in the running wave's fold, or a task line for the next wave. Anything larger: a task in the plan, through `plan-gate`. The change itself lands through the wave loop (`codex-review`, anti-slop pass, merge); this skill edits no factory file. Done: every accepted entry names the wave or the plan that carries it.
4. Mark each decided entry in place, `→ *<decision> (YYYY-MM-DD): <sentence>*`, and delete nothing; the file is the record. Done: no open entry from step 1 remains.

## Output

One line per decided entry, `<date> — <target file> — <decision> — <where it goes>`, then the deferred count (deferred entries are decided and marked; they reopen when the named information arrives).

## Limits

The decision is Fable's judgment on the entry's evidence; a suggestion whose source transcript has rotated out cannot be re-checked and is decided on the entry alone. Nothing here verifies that a routed task was built; the wave's verifier does.
