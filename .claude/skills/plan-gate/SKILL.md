---
name: plan-gate
description: Gate a plan before Codex sees it: premises, alternatives, existing-code leverage, pass/fail acceptance criteria, executability score. Fable fires it on every plan written after wave 2.
disable-model-invocation: true
---

# plan-gate

Runs on the plan document itself, before `codex-review` in plan mode. Each step ends with text in the plan; a step with nothing to write says so in one line.

## Procedure

1. Premises. Number every assumption the plan rests on, each phrased so it could be false ("the vault has no git" is a premise; "we need flexibility" is not). Confirm each against the repo or vault with `path:line`, or mark it unconfirmed and stop for the owner. Done: no premise is unconfirmed.
2. Alternatives. Write two or three approaches: one minimal-viable, one ideal, one lateral. Options differing only in naming are one option. Done: the chosen approach names the one it beat and why.
3. Leverage pass. Reuse-before-create (`.claude/rules/architecture.md`) on every part the plan creates, against the repo and the vault's `50-bootstrap/`. Done: nothing new is unexplained.
4. Acceptance criteria. Numbered, each pass/fail by a command or a read: "the gate works" fails the test; "three synthetic outputs return FAIL/FAIL/PASS" passes it. The plan also names the adjacent artifacts it allows (tests, migration, doc updates); an unlisted one reads as unasked-for in review. Done: every criterion names its evidence and the allowed-artifacts line exists.
5. Quantify or admit. Every size, count or time is a number with its source, or is marked "estimate" with what would firm it up. Done: no bare adjective of size remains.
6. "What is working well, do not touch": list the parts the plan leaves alone, so a reviewer can flag any drift into them. Done: the list exists, even when empty.
7. Anti-sycophancy read: remove any line whose job is to agree, praise or reassure ("absolutely", "you are right", "as requested"). Done: none left.
8. Executability score. Fable scores the plan 0–10: could an implementer with only this text execute it? Below 7, rewrite and rescore; at most three dispatches, then stop and ask the owner. Done: score and dispatch count written at the top of the plan.
9. Hand to `codex-review` in plan mode; the seam-inventory pre-flight (carrier table, bypass list) is in its prompt template.

## Output

The plan file carries each step's text. The gate report to the owner is five lines: premises confirmed N/N; approach chosen and beaten; new parts justified N/N; criteria N; score and dispatches. The report is a stop: implementation dispatches on the owner's go, never on the Codex verdict alone (AGENTS.md, canonical loop).

## Limits

The score is Fable's judgment, not a measurement; the Codex round is what checks it. The gate does not verify that premises stay true after the plan is written; a premise that changes reopens the plan (bounded autonomy, AGENTS.md).
