#!/usr/bin/env python3
"""PreToolUse guard for git commands (advisory scope guard, not a sandbox).

Deny tier: any `git push` unless the whole command is the four tokens
`git push origin main` (so no force push, no `factory`, no other remote or ref,
no `-C`/`--no-pager`/`command` prefix, no other command on the line). The
command is split on `;` `&&` `||` `|` and newlines, each segment tokenized with
shlex; a `git` token followed later in its segment by a `push` token is a push.
`$IFS`, `${IFS}`, a backslash-newline or an unbalanced quote deny outright.
Fails closed: an unparseable payload is denied.
Ask tier (same tokens): `reset --hard`, `clean -f`, `checkout .`, `restore .`.
Allow + log: `git commit` (placeholder until gates exist; see TODO below).

Smoke test (run from the repo root; expected decision after each):
  printf '%s' '{"tool_name":"Bash","tool_input":{"command":"git push origin main"}}' | python3 .claude/hooks/git-guard.py      # no output, exit 0 (allow)
  printf '%s' '{"tool_name":"Bash","tool_input":{"command":"git push origin factory"}}' | python3 .claude/hooks/git-guard.py   # permissionDecision deny
  printf '%s' '{"tool_name":"Bash","tool_input":{"command":"git push --force origin main"}}' | python3 .claude/hooks/git-guard.py  # deny
  printf '%s' '{"tool_name":"Bash","tool_input":{"command":"git -C x push origin main"}}' | python3 .claude/hooks/git-guard.py    # deny
  printf '%s' '{"tool_name":"Bash","tool_input":{"command":"git$IFS push origin main"}}' | python3 .claude/hooks/git-guard.py    # deny
  printf '%s' '{"tool_name":"Bash","tool_input":{"command":"git reset --hard; git push origin main"}}' | python3 .claude/hooks/git-guard.py  # deny
  printf '%s' '{"tool_name":"Bash","tool_input":{"command":"git reset --hard HEAD~1"}}' | python3 .claude/hooks/git-guard.py   # ask
  printf '%s' '{"tool_name":"Bash","tool_input":{"command":"git commit -m x"}}' | python3 .claude/hooks/git-guard.py           # exit 0, one line appended to .claude/.curate/git-guard.log
  printf 'not json' | python3 .claude/hooks/git-guard.py                                                                        # deny (fails closed)
"""
import json
import os
import re
import shlex
import sys
from datetime import datetime, timezone

SEGMENT = re.compile(r"\n|;|&&|\|\||\|")
OBFUSCATED = re.compile(r"\$\{?IFS\}?|\\\n")
ALLOWED_PUSH = ["git", "push", "origin", "main"]
ASK = [  # (subcommand, predicate over the tokens after it, reason)
    ("reset", lambda a: "--hard" in a, "git reset --hard discards work"),
    ("clean", lambda a: any(re.fullmatch(r"-[A-Za-z]*f[A-Za-z]*", t) or t == "--force" for t in a),
     "git clean -f deletes untracked files"),
    ("checkout", lambda a: "." in a, "discards every unstaged change"),
    ("restore", lambda a: "." in a, "discards every unstaged change"),
]


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
    if OBFUSCATED.search(command):
        decide("deny", "git-guard: $IFS or backslash-newline in a command is obfuscation; denied")
        return 0
    try:
        segments = [shlex.split(s) for s in SEGMENT.split(command)]
    except ValueError:
        decide("deny", "git-guard: unbalanced quote; cannot tokenize, denied (fails closed)")
        return 0
    git_args = [seg[seg.index("git") + 1:] for seg in segments if "git" in seg]  # tokens after `git`
    if any("push" in a for a in git_args):
        if segments != [ALLOWED_PUSH]:
            decide("deny", f"git-guard: only the exact command `{' '.join(ALLOWED_PUSH)}` may push; "
                   "no force push, no other remote or ref, and `factory` is never pushed (AGENTS.md, Repo state and git)")
        return 0
    for sub, hits, reason in ASK:
        if any(sub in a and hits(a[a.index(sub) + 1:]) for a in git_args):
            decide("ask", f"git-guard: {reason}; confirm before running")
            return 0
    if any("commit" in a for a in git_args):
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
