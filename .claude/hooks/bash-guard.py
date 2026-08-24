#!/usr/bin/env python3
"""PreToolUse guard for destructive Bash (advisory scope guard, not a sandbox).

Deny tier (fails closed on an unreadable payload): a recursive forced `rm` whose
target is `/`, `~` or `$HOME`, and the WSL2 / Postgres / Docker / uv patterns
listed in DENY. `rm` is judged on tokens: the command is split on `;` `&&` `||`
`|` and newlines, each segment tokenized with shlex, and `--` before the target
is ignored. `$IFS`, `${IFS}` or a backslash-newline deny outright.
Ask tier: any other `rm` with both -r and -f; a command shlex cannot tokenize
(an unbalanced quote, e.g. a heredoc containing an apostrophe).

Smoke test (run from the repo root; expected decision after each):
  printf '%s' '{"tool_name":"Bash","tool_input":{"command":"rm -rf ./build"}}' | python3 .claude/hooks/bash-guard.py     # ask
  printf '%s' '{"tool_name":"Bash","tool_input":{"command":"rm -rf /"}}' | python3 .claude/hooks/bash-guard.py           # deny
  printf '%s' '{"tool_name":"Bash","tool_input":{"command":"rm -rf -- /"}}' | python3 .claude/hooks/bash-guard.py        # deny
  printf '%s' '{"tool_name":"Bash","tool_input":{"command":"rm$IFS-rf$IFS/"}}' | python3 .claude/hooks/bash-guard.py     # deny
  printf '%s' '{"tool_name":"Bash","tool_input":{"command":"rm -rf $HOME"}}' | python3 .claude/hooks/bash-guard.py       # deny
  printf '%s' '{"tool_name":"Bash","tool_input":{"command":"cat <<EOF\nit'"'"'s fine\nEOF"}}' | python3 .claude/hooks/bash-guard.py  # ask (unbalanced quote)
  printf '%s' '{"tool_name":"Bash","tool_input":{"command":"docker compose down -v"}}' | python3 .claude/hooks/bash-guard.py  # deny
  printf '%s' '{"tool_name":"Bash","tool_input":{"command":"ls -la"}}' | python3 .claude/hooks/bash-guard.py             # no output, exit 0 (allow)
  printf 'not json' | python3 .claude/hooks/bash-guard.py                                                                # deny (fails closed)
"""
import json
import re
import shlex
import sys

SEGMENT = re.compile(r"\n|;|&&|\|\||\|")
OBFUSCATED = re.compile(r"\$\{?IFS\}?|\\\n")
WIPE_ROOTS = {"/", "~", "$HOME", "${HOME}"}
DENY = [
    (re.compile(r"\bDROP\s+(?:DATABASE|SCHEMA|TABLE)\b", re.IGNORECASE), "dropping a Postgres database, schema or table"),
    (re.compile(r"\bTRUNCATE\s+(?:TABLE\s+)?\w", re.IGNORECASE), "truncating a Postgres table"),
    (re.compile(r"\balembic\s+downgrade\b"), "alembic downgrade rewinds the schema"),
    (re.compile(r"\bdocker\s+volume\s+(?:rm|prune)\b"), "removing Docker volumes (the Postgres data lives there)"),
    (re.compile(r"\bdocker\s+compose\s+down\s+(?:\S+\s+)*(?:-v|--volumes)\b"), "docker compose down with volumes deletes the database"),
    (re.compile(r"\bdocker\s+system\s+prune\b"), "docker system prune"),
    (re.compile(r"\buv\s+cache\s+clean\s*(?:$|[;&|])"), "uv cache clean with no package wipes the whole cache"),
    (re.compile(r"\b(?:mkfs\b|dd\s+(?:\S+\s+)*of=/dev/)"), "formatting or raw-writing a block device"),
    (re.compile(r"\bwsl(?:\.exe)?\s+--unregister\b"), "wsl --unregister destroys the distro"),
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
        decide("deny", "bash-guard: unreadable hook payload; denied (fails closed)")
        return 0
    if not isinstance(command, str):
        decide("deny", "bash-guard: tool_input.command is not a string; denied (fails closed)")
        return 0
    if OBFUSCATED.search(command):
        decide("deny", "bash-guard: $IFS or backslash-newline in a command is obfuscation; denied")
        return 0
    for pattern, reason in DENY:
        if pattern.search(command):
            decide("deny", f"bash-guard: {reason}; run it yourself outside the agent if you mean it")
            return 0
    try:
        segments = [shlex.split(s) for s in SEGMENT.split(command)]
    except ValueError:
        decide("ask", "bash-guard: could not parse command; review manually")
        return 0
    rm_rf = False
    for args in [seg[seg.index("rm") + 1:] for seg in segments if "rm" in seg]:
        flags = [t for t in args if t.startswith("-") and t != "--"]
        recursive = any(t == "--recursive" or re.fullmatch(r"-[a-zA-Z]*[rR][a-zA-Z]*", t) for t in flags)
        force = any(t == "--force" or re.fullmatch(r"-[a-zA-Z]*f[a-zA-Z]*", t) for t in flags)
        if not (recursive and force):
            continue
        rm_rf = True
        targets = args[args.index("--") + 1:] if "--" in args else [t for t in args if not t.startswith("-")]
        for t in targets:
            if ((t[:-1] if t.endswith("*") else t).rstrip("/") or "/") in WIPE_ROOTS:
                decide("deny", "bash-guard: rm -rf on the filesystem root or home directory; "
                       "run it yourself outside the agent if you mean it")
                return 0
    if rm_rf:
        decide("ask", "bash-guard: recursive forced delete; confirm the target before running")
    return 0


if __name__ == "__main__":
    sys.exit(main())
