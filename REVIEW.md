# REVIEW.md — reviewer contract for this repo

Applies to every reviewer: Codex (`codex exec`, the default diff reviewer), the
in-house `peer-reviewer` agent, and any ad-hoc review pass.

- Flag only gaps that affect **correctness or the stated requirements**; treat
  style, coverage, and "robustness" suggestions as optional observations.
- Report **at most five nits**; count the rest.
- **Skip anything ruff / Biome / tsc already enforces** — the gates run in CI,
  a reviewer repeating them is noise.
- Behaviour claims need a **`file:line` citation**.
- After the first round, post **Important findings only** — do not introduce new
  nits on re-review.
- Over-engineering signals to flag **as findings** (not nits):
  - **RED (blocker):** 3+ files for a simple feature; a new pattern for a
    one-off; "future flexibility"; a helper with one call site; a class with no
    instance state.
  - **YELLOW (observation with teeth):** Manager/Handler/Service proliferation;
    config for constants; middleware for a linear flow; try/catch around calls
    that should propagate; backward-compat shims where the code could just
    change.
- Never ask for error handling, scalability, migration strategy or backward
  compatibility unless the task statement requires them. **A diff that could be
  smaller is a finding.**
- The simplicity rules in `.claude/rules/` outrank a reviewer's request for
  broader coverage — see the precedence rule there. The reviewer judges; the
  implementer doesn't grade its own work.
