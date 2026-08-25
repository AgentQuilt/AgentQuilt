---
name: codex-review
description: Run a Codex peer review of a wave diff or a plan through the fail-closed verdict gate. Fable fires it after every implementation wave and, for plans, after plan-gate.
disable-model-invocation: true
---

# codex-review

The contract is `REVIEW.md`; the prompt (`references/prompt-template.md`) inlines it and the AGENTS.md calibration paragraph.

## Procedure (one round)

1. Write `temp/<wave>_review_context.md`: the wave brief and the task lines the task-fidelity axis quotes; on round N>1, append what round N-1's findings became (folded, or argued away in one sentence). Done: the file names every task line.
2. Run from the wave checkout: `bash .claude/skills/codex-review/scripts/review.sh diff <wave> [base] [round]` or `... plan <wave> <file> [round]`; prompt and output land in `temp/`. Done: a `VERDICT:` line printed under `--- gate ---`.
3. Read the reviewer output, then write one line before touching anything: `Recommendation: <action> because <finding>`. Done: the line quotes a finding or `NO FINDINGS`.
4. Fold: every P1; every P2 unless argued away in one sentence in the next context file. Done: one commit per round with the round number in the message.
5. Re-run; before reusing an old verdict, `review.sh check temp/<wave>_<mode>_review_rN.md` says whether it still binds (content hash of the tree, and the plan file in plan mode, stamped before the review ran).

## Gate

In the script; every doubt is FAIL. Only the tag grammar in the template counts.

## Stop rule

Stop at PASS, or at no P1 with the remaining P2s accepted and written down. Round 4 is the cap: state the cost and stop; a fifth round runs only on the owner's word, given after the cost is stated. A degenerate round (cosmetic findings only, still FAIL) is discarded and re-run with a fresh prompt. An expanding frontier (consecutive FAILs each naming a new actor, a new file, or a new case in the same function) means the design shape is wrong: back to the plan, not another fold.

## Error taxonomy

| Symptom | Meaning | Do |
|---|---|---|
| Exit within seconds, usage text in `temp/*.log` | argument or flag error, no model was reached | fix the invocation; the round did not count |
| Exit 124 after the timeout, log quiet | model stall | re-run once; a second stall is a Codex outage, use the in-house `reviewer` |
| `400` / "model not supported" in the log | the model name is wrong or gone | the gate says FAIL; fix `-m`; never read this as PASS |
| Output present, no `VERDICT:` line | reviewer ignored the contract | FAIL by the gate; re-run with the context file naming the missing line |

## Cross-model arbitration

When Codex and the in-house `reviewer` both ran, record per finding: Codex-only (fold if P1; else judge), in-house-only (fold if P1 and it quotes the line; else judge), both (fold). A disagreement on severity keeps the higher one.

## Limits

The artefact is the tracked diff from the merge-base of the current checkout; untracked files stop the preflight (exit 2, no round spent). The gate greps line-anchored tags (`^P1 `), so prose such as "no P1" does not trip it; a finding written off-template is invisible to the gate and needs a human read.
