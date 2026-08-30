---
name: anti-slop
description: The implementer's self-check on its own diff before the report, and Fable's closing pass on the wave diff before merge: abstraction criterion, deletion test, reuse-before-create, stop conditions, Done/Left out. Not for prose; public copy goes to the humanizer chain.
---

# anti-slop

Run once, on your own diff, before the implementer report. The rules it applies live
elsewhere: simplicity in `rules/python.md` and `rules/typescript.md`, the architecture
checks in `rules/architecture.md`, severities in `REVIEW.md`, budgets in ruff and Biome.

## Before you write

1. Open the nearest exemplar module and copy its shape. Done: the exemplar's path is in the report.
2. reuse-before-create (`rules/architecture.md`) for each function, class or module you plan to create. Done: the closest existing part, and why it does not fit, is in the change description.

## Stop and ask instead of guessing

Stop when any line applies; report what you have plus the question.

- The request says should, might or maybe, or has more than one reading.
- The change is heading well past the plan's task lines in files or size. Say so in the report and propose a smaller cut; a migration, a test or a docs line the task needs is not overshoot.
- You are about to delete code that might still be used.
- The task is a refactor and a test assertion would have to change. That is a behaviour change; say which one.
- You are filling a gap with an assumption about intent. Write "I am assuming X" and ask.

## On the finished diff

1. Abstraction criterion: for each layer, wrapper, option or fallback you added, name its current consumer and the test that protects the contract. Done: both named, or the addition is gone.
2. deletion-test and one-adapter-seam, by name, on every new module and seam and on every function, branch or option the diff adds to an existing one. Done: a verdict per module.
3. Third-copy rule (`rules/python.md`, `rules/typescript.md`). Done: no half-extracted pair.
4. Walk `references/patterns.md`. Done: each hit fixed, none argued in the report.
5. Every changed line traces to a task line. Done: `git diff --stat` shows no file the task did not name.

## Output contract

The report ends with two sections:

- `Done:` what you built; for each new part, the existing part reused or the one-sentence reason nothing fit.
- `Left out:` what you chose not to build.

Prose published under the owner's name is routed by `references/prose.md`; metrics and
the model-assumption-ledger entry are in `references/measure.md`.

## Closing pass (Fable, after codex-review PASS, before merge)

Fable runs the "On the finished diff" list once more on the wave diff, with the plan's task lines and the Codex findings open. Done: every hunk names its task line or is cut; nothing is added, and no new finding is raised that Codex did not (the pass reduces, it does not review).

## Success test

Two consecutive wave diffs carry no P1 of a named kind (`REVIEW.md`, Architecture axis) in round 1. The same kind on two consecutive diffs means the line here that should have caught it is broken: fix the line, not only the diff.

## Limits

A self-check by the author of the diff; it replaces no review. Reviewer judgement is
`REVIEW.md`, lint is the gates.
