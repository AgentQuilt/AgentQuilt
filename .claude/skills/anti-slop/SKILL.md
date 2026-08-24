---
name: anti-slop
description: The implementer's self-check on its own diff before the report: abstraction criterion, deletion test, reuse-before-create, stop conditions, Done/Left out. Not for prose; public copy goes to the humanizer chain.
---

# anti-slop

Run once, on your own diff, before the implementer report. The rules it applies live
elsewhere: simplicity in `rules/python.md` and `rules/typescript.md`, the architecture
checks in `rules/architecture.md`, severities in `REVIEW.md`, budgets in ruff and Biome.
This pass exists so the reviewer finds less.

## Before you write

1. Open the nearest exemplar module and copy its shape. Done: the exemplar's path is in the report.
2. reuse-before-create (`rules/architecture.md`): for each function, class or module you plan to create, name the closest existing part and why composing or extending it fails. Done: that sentence is in the change description.

## Stop and ask instead of guessing

Stop when any line applies; report what you have plus the question.

- The request says should, might or maybe, or has more than one reading.
- The change is heading past five files, or past ~500 changed lines of non-mechanical work. Propose a smaller cut.
- You are about to delete code that might still be used.
- The task is a refactor and a test assertion would have to change. That is a behaviour change; say which one.
- You are filling a gap with an assumption about intent. Write "I am assuming X" and ask.

## On the finished diff

1. Abstraction criterion: for each layer, wrapper, option or fallback you added, name its current consumer and the test that protects the contract. Done: both named, or the addition is gone.
2. deletion-test and one-adapter-seam, by name, on every new module and seam in the diff. Done: a verdict per module.
3. Three similar lines: extraction happens on the third copy and is finished. Done: no half-extracted pair.
4. Walk `references/patterns.md`. Done: each hit fixed, none argued in the report.
5. Every changed line traces to a task line. Done: `git diff --stat` shows no file the task did not name.

## Output contract

The report ends with two sections, always:

- `Done:` what you built; for each new part, the existing part reused or the one-sentence reason nothing fit.
- `Left out:` what you chose not to build, so restraint is visible.

Prose published under the owner's name is routed by `references/prose.md`; metrics and
the model-assumption-ledger entry are in `references/measure.md`.

## Success test

The next `codex-review` round on the diff carries no P1 of kind deletion-test,
one-adapter-seam, reuse-before-create or a simplicity-axis P1 signal, and at most two
simplicity-axis P2 (threshold proposed, 2026-08-24). Verifier, kinds as REVIEW.md names them:
`grep -cE '^P1 .*(deletion-test|one-adapter-seam|reuse-before-create|3\+ files|one-off|future flexibility|one call site|no instance state)' temp/<wave>_diff_review_r1.md` returns 0;
`grep -cE '^P2 .*(proliferation|config for constants|middleware|try/catch|backward-compat)' temp/<wave>_diff_review_r1.md` returns at most 2.
The same kind on two consecutive diffs means the line here that should have caught it
is broken: fix the line, not only the diff.

## Limits

A self-check by the author of the diff; it lowers the reviewer's count and replaces no
review. It sees column A only: reviewer judgement is `REVIEW.md`, lint is the gates.
