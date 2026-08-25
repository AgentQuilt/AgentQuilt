---
paths: [".claude/hooks/**", ".claude/settings.json"]
---

# Hook authoring invariants

- Every hook's header comment records its piped smoke test (command and expected exit code or decision); rerun it after any edit.
- Hooks are advisory scope guards, not a sandbox; worktree isolation is the real isolation. Ref protection lives in the git-native `pre-push` hook, which sees the real ref and cannot be quoted around.
- No PreToolUse command guards: a guard that parses shell text re-implements the shell and fails on ordinary text (removed 2026-08-25, decision log). A new PreToolUse hook is an owner decision, not a wave.
