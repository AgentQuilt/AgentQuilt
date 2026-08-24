#!/usr/bin/env python3
"""PreToolUse guard for git commands (advisory scope guard, not a sandbox).

Deny tier: any `git push` other than exactly `git push origin main` (so no
force push, no `factory`, no other remote or ref). Fails closed: an unparseable
payload is denied.
Ask tier: `reset --hard`, `clean -f`, `checkout .`, `restore .`.
Allow + log: `git commit` (placeholder until gates exist; see TODO below).

Smoke test (run from the repo root; expected decision after each):
  printf '%s' '{"tool_name":"Bash","tool_input":{"command":"git push origin main"}}' | python3 .claude/hooks/git-guard.py      # no output, exit 0 (allow)
  printf '%s' '{"tool_name":"Bash","tool_input":{"command":"git push origin factory"}}' | python3 .claude/hooks/git-guard.py   # permissionDecision deny
  printf '%s' '{"tool_name":"Bash","tool_input":{"command":"git push --force origin main"}}' | python3 .claude/hooks/git-guard.py  # deny
  printf '%s' '{"tool_name":"Bash","tool_input":{"command":"git reset --hard HEAD~1"}}' | python3 .claude/hooks/git-guard.py   # ask
  printf '%s' '{"tool_name":"Bash","tool_input":{"command":"git commit -m x"}}' | python3 .claude/hooks/git-guard.py           # exit 0, one line appended to .claude/.curate/git-guard.log
  printf 'not json' | python3 .claude/hooks/git-guard.py                                                                        # deny (fails closed)
"""
import json
import os
import re
import sys
from datetime import datetime, timezone

PUSH = re.compile(r"\bgit\s+push\b")
ALLOWED_PUSH = "git push origin main"
ARG = r"(?:[^\s;&|]+\s+)*"  # options and refs of one simple command
ASK = [
    (re.compile(r"\bgit\s+reset\s+" + ARG + r"--hard\b"), "git reset --hard discards work"),
    (re.compile(r"\bgit\s+clean\s+" + ARG + r"-[A-Za-z]*f"), "git clean -f deletes untracked files"),
    (re.compile(r"\bgit\s+(?:checkout|restore)\s+" + ARG + r"\.(?=\s|$|[;&|])"), "discards every unstaged change"),
]
COMMIT = re.compile(r"\bgit\s+commit\b")


def decide(decision: str, reason: str) -> None:
    print(json.dumps({"hookSpecificOutput": {
        "hookEventName": "PreToolUse",
        "permissionDecision": decision,
        "permissionDecisionReason": reason,
    }}))


def main() -> int:
    try:
        payload = json.loads(sys.stdin.read())
        command = payload["tool_input"]["command"] if payload.get("tool_name") == "Bash" else ""
    except Exception:
        decide("deny", "git-guard: unreadable hook payload; denied (fails closed)")
        return 0
    if not isinstance(command, str):
        decide("deny", "git-guard: tool_input.command is not a string; denied (fails closed)")
        return 0
    if PUSH.search(command):
        if command.strip() != ALLOWED_PUSH:
            decide("deny", f"git-guard: only the exact command `{ALLOWED_PUSH}` may push; "
                   "no force push, no other remote or ref, and `factory` is never pushed (AGENTS.md, Repo state and git)")
        return 0
    for pattern, reason in ASK:
        if pattern.search(command):
            decide("ask", f"git-guard: {reason}; confirm before running")
            return 0
    if COMMIT.search(command):
        # TODO(gates): once the review gate writes .claude/.gate/PASSED, replace the log line with
        # the deny documented in the mechanics research, section 4.5 route B:
        #   if not os.path.isfile(os.path.join(project_dir, ".claude", ".gate", "PASSED")):
        #       decide("deny", "git commit requires the review gate to pass")
        # The JSON emitted is {"hookSpecificOutput": {"hookEventName": "PreToolUse",
        #   "permissionDecision": "deny", "permissionDecisionReason": "git commit requires the review gate to pass"}}
        project_dir = os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd()
        log_dir = os.path.join(project_dir, ".claude", ".curate")
        os.makedirs(log_dir, exist_ok=True)
        with open(os.path.join(log_dir, "git-guard.log"), "a", encoding="utf-8") as log:
            log.write(json.dumps({"ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                                  "allowed": "commit", "command": command}) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
