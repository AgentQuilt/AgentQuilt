# REVIEW.md — reviewer contract

Applies to every reviewer: Codex (`codex exec`, the default diff reviewer), the
in-house `reviewer` agent, and any ad-hoc pass. Procedure (prompt files, rounds,
fold discipline) lives in the `codex-review` skill; this file is the contract.

## Severity, one scheme

- P1 blocks: incorrect, violates a stated requirement, or fails a named kind below. P2 is an observation with teeth: fold it or argue it away in one sentence. P3 is a nit: report at most five, count the rest.
- Every finding carries `file:line` and its kind by name. End with one line, `VERDICT: PASS` or `VERDICT: FAIL`; any P1 means FAIL.
- Mapping for older material: RED is P1 and YELLOW is P2; no other file uses those words.
- After round 1, report P1 and P2 only; no new nits on re-review.
- The reviewer never edits what it reviews. It judges; the implementer does not grade its own work, and a stated rationale never lowers severity.

## Simplicity axis

- Flag only gaps that affect correctness or the stated requirements; style, coverage and "robustness" are P3 at most.
- Skip anything ruff / Biome / tsc already enforces; the gates run it, a reviewer repeating it is noise.
- P1 signals: 3+ files for a simple feature; a new pattern for a one-off; "future flexibility"; a helper with one call site; a class with no instance state.
- P2 signals: Manager/Handler/Service proliferation; config for constants; middleware for a linear flow; try/catch around calls that should propagate; backward-compat shims where the code could just change.
- Never ask for error handling, scalability, migration strategy or backward compatibility unless the task statement requires them. A diff that could be smaller is a finding.
- The simplicity rules in `.claude/rules/` outrank a reviewer's request for broader coverage (precedence rule, AGENTS.md). Flag over-engineering in your own suggestions.

## Architecture axis (P1 kinds; the wording lives in `.claude/rules/architecture.md`)

- deletion-test: not stated, or fails, for a new module.
- one-adapter-seam: a seam with one adapter; a port around a pure function or an in-process dependency.
- tests-past-interface: tests reach past the interface; a deepened module whose old shallow tests survive.
- design-it-twice: a major seam chosen without genuinely different alternatives.
- judgment-as-code: a heuristic decision tree where a skill should decide.
- vocabulary: a design word outside the design-rules set; a domain name without a glossary entry; a kernel concept, seam, registry field or ledger event kind without an ADR number.
- map-outdated: the change outdates `INDEX.md` / `MODULE.md` without updating it.
- reuse-before-create: a new part where an existing one could be composed or extended, or created without naming the closest existing part and why it does not fit.
- tautological-test: a test that restates the implementation.

## Task-fidelity axis

- missing: a task line not delivered. unasked-for: behaviour not in the task statement. wrong: delivered, but not what the line says. Quote the task line in each finding.
