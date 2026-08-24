---
paths: [".claude/hooks/**", ".claude/settings.json"]
---

# Hook authoring invariants

- A decision goes under `hookSpecificOutput` (`hookEventName`, `permissionDecision`, `permissionDecisionReason`); a top-level `permissionDecision` is ignored and the deny silently no-ops.
- Parse the payload with python's `json`, never grep or regex it; a quoted command truncates at the first escaped quote.
- Build output with `json.dumps`; never interpolate a path or command into hand-built JSON, since a quote or newline makes the deny malformed and ignored.
- Failure polarity by tier: an ask-tier hook fails to `ask` on an unparseable payload; a deny-tier hook fails to `deny`. A guard that fails open is not a guard.
- Resolve symlinks through the final path component before comparing paths, and compare with a trailing `/` so `/src` never matches `/src-old`.
- Every hook's header comment records its piped-JSON smoke test (command and expected exit code or decision); rerun it after any edit.
- Hooks are advisory scope guards, not a sandbox; worktree isolation is the real isolation.
