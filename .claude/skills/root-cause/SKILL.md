---
name: root-cause
description: Trace a failing behaviour to its cause before any fix: capped hypotheses and fixes, a regression test, tagged logs. The implementer fires it on bugs; not for features or refactors.
---

# root-cause

Fires when the implementer meets behaviour that contradicts a spec, a test or a report. The fix is the last step; everything before it is finding out why. Defense-in-depth is allowed here and nowhere else (AGENTS.md, Code simplicity).

## Procedure

1. Loop first: one command that shows the failure, already run once, deterministic, fast enough to run after every change, with no human in the middle. Done: the command and its red output are in the notes; without a red command no hypothesis is written.
2. Shrink the reproduction until removing anything more makes it pass. Done: the smallest input, state and call path are written down.
3. Hypotheses: three to five, ranked, each in the form "if X is the cause, changing Y will show Z". Done: the list exists before any of them is tested.
4. Test one hypothesis per run, one variable per change. Debug output carries a tag (`[RC-<4 hex>]`) so one grep finds all of it. Done: each hypothesis marked confirmed or refuted, with the output that decided it.
5. Regression test at the seam the architect named or through the interface the caller uses (tests-past-interface, `.claude/rules/architecture.md`): it fails on the current code and passes with the fix. No seam to put it on is itself the finding: report it as a task for `architect`. Done: red run and green run pasted.
6. Fix the cause with the smallest change that turns the test green; the surrounding code stays as it was. Done: the diff touches the cause and the test, nothing else.
7. Cleanup: reproduction green, regression test kept, every `[RC-` tag gone (the grep prints nothing), throwaway scripts deleted, the confirmed hypothesis in the commit message. Done: each item checked off in the report.

## Caps

- Three refuted hypotheses: stop, no fourth. Report the three with their evidence and three options (widen the loop, ask the owner for context, hand the seam to `architect`).
- Three fixes that did not hold: the shape is wrong, not the guess. Stop and hand the seam to `architect` with the three attempts.
- A fix heading past five files meets the `anti-slop` stop condition; stop there and propose the smaller cut.
- Before any web search, strip hostnames, paths, identifiers and data from the error text and search the error category (AGENTS.md, Provenance boundary).

## Output contract

Failing command and output · minimal reproduction · hypotheses with verdicts · regression test path with red and green output · fix summary · cleanup checklist · `Done:` and `Left out:`. On a cap: the stop and the options, no fix.

## Limits

Dormant until code exists: there is no command to run red before the first scaffold. It finds causes in code it can run; a failure that shows only in production or a browser goes to the owner or `browser-qa` for the reproduction first. The step order and the cleanup list follow mattpocock/skills `diagnosing-bugs`; the text is rewritten. Adapted from mattpocock/skills (MIT).
