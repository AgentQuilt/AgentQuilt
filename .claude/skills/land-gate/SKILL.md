---
name: land-gate
description: Pre-merge check that a wave branch carries fresh verification evidence, merged-state gates, matching docs and a clean worktree. Fable fires it after codex-review PASS; not a review.
---

# land-gate

Runs once on a wave branch after `codex-review` PASS and the `verifier` report, before the merge into `factory` (AGENTS.md, Git and branches).

## Evidence rule

A completion claim counts only with verification output produced after the last change and pasted into the report.

| Claim | Stop |
|---|---|
| "should work", "I am confident" | run the command, paste the output |
| "I tested it earlier" | the tree changed since; run it again |
| "trivial change", "only docs" | same gates, same paste |
| "the reviewer already passed it" | step 4 decides that, not the memory of it |

## Procedure

1. `git -C <path> branch --show-current` prints the wave branch and `git -C <path> status --short` prints nothing. Done: both outputs pasted; a dirty tree or the base branch stops here.
2. `git -C <path> rebase factory` (waves carry no merge commits). A conflict stops with the conflict shown. Done: `git merge-base --is-ancestor factory HEAD` holds.
3. Gates on the rebased tree: the commands in AGENTS.md (Gates), each output read against its trap. Done: output pasted; a red gate stops here.
4. Review still binds: `bash .claude/skills/codex-review/scripts/review.sh check temp/<wave>_diff_review_rN.md` on the rebased tree. Done: the check passes, or one more `codex-review` round runs and the gate restarts at step 1.
5. Docs match the diff: walk `git diff --stat`; for every part added, changed or removed, the line that describes it (INDEX.md, AGENTS.md, the roster, a MODULE.md, a docs page) says what the tree now does (map-outdated, `.claude/rules/architecture.md`). Done: each part has a current line; a gap is HOLD, listed in the report.
6. Report matches the commits: the implementer's `Done:` names nothing absent from `git log factory..<branch>` and omits nothing present.
7. Run step 4's `check` once more immediately before merging (a stale hash restarts at step 1), merge per the AGENTS.md git rules, then `git worktree remove <path>` only when `git -C <path> status --short` prints nothing and the path is not the main checkout; never `--force`. Done: `git worktree list` no longer shows the path; a dirty worktree stays and is reported.

## Output contract

Per step: command, output excerpt, `PASS | STOP`. One line `VERDICT: LAND | HOLD`; for HOLD, the step and the next action ("review stale: one codex-review round, then back to step 1").

## Limits

One pass. Dormant until code exists: steps 3 and 4 have nothing to run before the first scaffold; until then the gate is steps 1, 2, 5, 6 and 7. It fixes nothing: a defect goes back to `codex-review` and the implementer.
