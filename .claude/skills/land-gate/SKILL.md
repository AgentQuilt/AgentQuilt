---
name: land-gate
description: Pre-merge check that a wave branch carries fresh verification evidence, merged-state gates, matching docs and a clean worktree. Fable fires it after codex-review PASS; not a review.
disable-model-invocation: true
---

# land-gate

Runs once on a wave branch after `codex-review` says PASS and the `verifier` has reported, before the merge into `factory` (AGENTS.md, Repo state and git). It checks evidence; the only output it produces is that of the commands below.

## Evidence rule

A completion claim counts only with verification output produced after the last change and pasted into the report. "Should work", "I am confident", "I tested it earlier" and "it is a trivial change" are claims: the answer to each is to run the command again and paste what it printed. Any change to the tree after a run invalidates that run.

## Procedure

1. Preflight: `git -C <path> branch --show-current` prints the wave branch and `git -C <path> status --short` prints nothing. Done: both outputs pasted; a dirty tree or the base branch stops here.
2. Merge the base first: `git -C <path> merge factory`. A conflict that needs judgment stops with the conflict shown; the gate resolves nothing. Done: the tree contains the tip of `factory`.
3. Gates on the merged state: the commands in AGENTS.md (Gates), each output read against its trap. Done: output pasted; a red gate stops here.
4. Review still binds: `bash .claude/skills/codex-review/scripts/review.sh check temp/<wave>_diff_review_rN.md` on the merged tree. Done: the check passes, or one more `codex-review` round runs and the gate restarts at step 1.
5. Docs match what shipped: for each skill, agent, hook or command the diff adds, INDEX.md, AGENTS.md or the roster carries its line (map-outdated, `.claude/rules/architecture.md`). Done: every added part has its line, or the gap is listed.
6. Report matches the commits: the implementer's `Done:` names nothing absent from `git log factory..<branch>` and omits nothing present. Done: both directions checked.
7. Merge per the AGENTS.md git rules, then `git worktree remove <path>` only when `git -C <path> status --short` prints nothing and the path is not the main checkout; never `--force`. Done: `git worktree list` no longer shows the path; a dirty worktree stays and is reported.

## Output contract

Per step: command, output excerpt, `PASS | STOP`. One line `VERDICT: LAND | HOLD`; for HOLD, the step and the next action ("review stale: one codex-review round, then back to step 1").

## Limits

One pass; watching the merged branch afterwards is a separate invocation. Dormant until code exists: steps 3 and 4 have nothing to run before the gate commands land with the first scaffold, so until then the gate is steps 1, 2, 5, 6 and 7. It fixes nothing: a defect it notices goes back to `codex-review` and the implementer.
