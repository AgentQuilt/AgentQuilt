#!/usr/bin/env python3
"""PreToolUse guard for git commands.

Deny tier: any `git push` unless the whole command is exactly `git push origin main`
(no force push, no `factory`, no other remote or ref, no `-C`/`--no-pager`/`command`
prefix, nothing else on the line). A `push` token counts only where something could run
it (`PUSH_PROGRAMS`, a `$var` program or a here-string) and never as a git message
argument (`-m x`, `-mx`, `-am"x"`, `--message=x`), so a commit message may say "push". `$IFS`, a backslash-newline, an
unbalanced quote or an unreadable payload deny outright (fails closed). A heredoc body
becomes one quoted token, so its apostrophes parse and its `push` is still seen; an
opener inside quotes (`echo '<<EOF'`) is data and opens no body.
Ask tier: `reset --hard`, `clean -f`, `checkout .`, `restore .`.
Allow + log: `git commit` (placeholder until the review gate exists; see TODO).

Smoke test (run from the repo root; expected decision after each).
Run them all: sed -n 's/^  printf/printf/p' .claude/hooks/git-guard.py | bash
  printf '%s' '{"tool_name":"Bash","tool_input":{"command":"git push origin main"}}' | python3 .claude/hooks/git-guard.py      # no output, exit 0 (allow)
  printf '%s' '{"tool_name":"Bash","tool_input":{"command":"git push origin factory"}}' | python3 .claude/hooks/git-guard.py   # permissionDecision deny
  printf '%s' '{"tool_name":"Bash","tool_input":{"command":"git push --force origin main"}}' | python3 .claude/hooks/git-guard.py  # deny
  printf '%s' '{"tool_name":"Bash","tool_input":{"command":"git -C x push origin main"}}' | python3 .claude/hooks/git-guard.py    # deny
  printf '%s' '{"tool_name":"Bash","tool_input":{"command":"git$IFS push origin main"}}' | python3 .claude/hooks/git-guard.py    # deny
  printf '%s' '{"tool_name":"Bash","tool_input":{"command":"git reset --hard; git push origin main"}}' | python3 .claude/hooks/git-guard.py  # deny
  printf '%s' '{"tool_name":"Bash","tool_input":{"command":"sh -c \"git push origin factory\""}}' | python3 .claude/hooks/git-guard.py    # deny (wrapper shell)
  printf '%s' '{"tool_name":"Bash","tool_input":{"command":"g=git; $g push origin factory"}}' | python3 .claude/hooks/git-guard.py    # deny ($var program)
  printf '%s' '{"tool_name":"Bash","tool_input":{"command":"bash <<< \"git push origin factory\""}}' | python3 .claude/hooks/git-guard.py  # deny (here-string)
  printf '%s' '{"tool_name":"Bash","tool_input":{"command":"sh <<'"'"'EOF'"'"'\ngit push origin factory\nEOF"}}' | python3 .claude/hooks/git-guard.py  # deny (heredoc body is still scanned)
  printf '%s' '{"tool_name":"Bash","tool_input":{"command":"echo '"'"'<<EOF'"'"'; git push origin factory"}}' | python3 .claude/hooks/git-guard.py  # deny (a quoted `<<` opens no heredoc)
  printf '%s' '{"tool_name":"Bash","tool_input":{"command":"echo '"'"'<<EOF'"'"'\ngit push origin factory"}}' | python3 .claude/hooks/git-guard.py  # deny (same, on the next line)
  printf '%s' '{"tool_name":"Bash","tool_input":{"command":"git commit -m x; git push origin factory"}}' | python3 .claude/hooks/git-guard.py  # deny (the message ends at its segment)
  printf '%s' '{"tool_name":"Bash","tool_input":{"command":"git reset --hard HEAD~1"}}' | python3 .claude/hooks/git-guard.py   # ask
  printf '%s' '{"tool_name":"Bash","tool_input":{"command":"git clean -fd"}}' | python3 .claude/hooks/git-guard.py            # ask
  printf '%s' '{"tool_name":"Bash","tool_input":{"command":"git checkout ."}}' | python3 .claude/hooks/git-guard.py           # ask
  printf '%s' '{"tool_name":"Bash","tool_input":{"command":"git restore ."}}' | python3 .claude/hooks/git-guard.py            # ask
  printf '%s' '{"tool_name":"Bash","tool_input":{"command":"git commit -m x"}}' | python3 .claude/hooks/git-guard.py           # exit 0, one line appended to .claude/.curate/git-guard.log
  printf '%s' '{"tool_name":"Bash","tool_input":{"command":"git commit -m \"add push-guard\""}}' | python3 .claude/hooks/git-guard.py  # allow (-m argument is not scanned)
  printf '%s' '{"tool_name":"Bash","tool_input":{"command":"git commit -mpush"}}' | python3 .claude/hooks/git-guard.py     # allow (value attached to -m)
  printf '%s' '{"tool_name":"Bash","tool_input":{"command":"git commit -m=push"}}' | python3 .claude/hooks/git-guard.py    # allow (value attached with =)
  printf '%s' '{"tool_name":"Bash","tool_input":{"command":"git commit -am\"push this\""}}' | python3 .claude/hooks/git-guard.py  # allow (short-option cluster)
  printf '%s' '{"tool_name":"Bash","tool_input":{"command":"grep -rn push .claude/hooks/"}}' | python3 .claude/hooks/git-guard.py  # allow (grep cannot push)
  printf '%s' '{"tool_name":"Bash","tool_input":{"command":"grep -n \"the profile'"'"'s targets\" file"}}' | python3 .claude/hooks/git-guard.py  # allow (apostrophe inside a double-quoted string)
  printf '%s' '{"tool_name":"Bash","tool_input":{"command":"python3 - <<'"'"'EOF'"'"'\nit'"'"'s fine\nEOF"}}' | python3 .claude/hooks/git-guard.py  # allow (apostrophe in a heredoc body)
  printf '%s' '{"tool_name":"Bash","tool_input":{"command":"git status"}}' | python3 .claude/hooks/git-guard.py                # allow
  printf 'not json' | python3 .claude/hooks/git-guard.py                                                                        # deny (fails closed)
"""
import json
import os
import re
import shlex
import sys
from datetime import datetime, timezone

OBFUSCATED = re.compile(r"\$\{?IFS\}?|\\\n")
HEREDOC = re.compile(r"(?<!<)<<(?!<)\s*(['\"]?)(\w+)\1")
MESSAGE = re.compile(r"-[a-zA-Z]*m")  # a short-option cluster ending in m
VAR = re.compile(r"\$\{?\w")
SEPARATORS = set("();|&\n")  # `<`, `>` stay in the segment so a here-string is visible
PUSH_PROGRAMS = {"git", "sh", "bash", "zsh", "eval", "exec", "env", "command", "xargs"}
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


def heredoc_opener(line: str, quote: str) -> tuple[str | None, str]:
    """This line's first unquoted heredoc tag, and the quote state left open at its end.

    `quote` carries an open quote across lines. A `<<` inside quotes is data, so
    `echo '<<EOF'` opens no body and the line after it stays a command the guard reads.
    """
    tag, index = None, 0
    while index < len(line):
        char = line[index]
        if quote:
            if char == quote:
                quote = ""
            elif char == "\\" and quote == '"':
                index += 1
        elif char == "\\":
            index += 1
        elif char in "'\"":
            quote = char
        elif tag is None:
            opener = HEREDOC.match(line, index)
            if opener:
                tag, index = opener.group(2), opener.end() - 1
        index += 1
    return tag, quote


def parse(command: str) -> list[list[str]]:
    """Cut the command into segments at the shell operators; ValueError on an unbalanced quote.

    Each heredoc body (after `<<TAG`, `<<'TAG'` or `<<"TAG"`, up to the line equal to TAG)
    is first re-quoted into one token, so its apostrophes stop breaking the parse while its
    text stays scannable.
    """
    kept: list[str] = []
    body: list[str] = []
    tag = None
    quote = ""
    for line in command.split("\n"):
        if tag is not None:
            if line == tag:
                kept[-1] += " " + shlex.quote("\n".join(body))
                tag, body = None, []
            else:
                body.append(line)
            continue
        kept.append(line)
        tag, quote = heredoc_opener(line, quote)
    lexer = shlex.shlex("\n".join(kept), posix=True, punctuation_chars="();<>|&\n")
    lexer.whitespace = " \t\r"
    lexer.whitespace_split = True
    cut: list[list[str]] = [[]]
    for token in lexer:
        if token and set(token) <= SEPARATORS:
            cut.append([])
        else:
            cut[-1].append(token)
    return [seg for seg in cut if seg]


def pushes(seg: list[str]) -> bool:
    """A `push` token in a segment that could run one; a git message argument is not a push."""
    program = os.path.basename(seg[0])
    if not (program in PUSH_PROGRAMS or VAR.search(seg[0]) or "<<<" in seg):
        return False
    if program != "git":  # only git takes a message, so every other token counts
        return any("push" in token for token in seg)
    skip = False
    for token in seg:
        short = MESSAGE.match(token)
        if skip:
            skip = False
        elif token == "--message" or (short and short.end() == len(token)):
            skip = True  # `-m`, `-am`, `--message`: the message is the next token
        elif short or token.startswith("--message="):
            continue  # `-mx`, `-m=x`, `-am"x"`, `--message=x`: the message rides on the flag
        elif "push" in token:
            return True
    return False


def main() -> int:
    try:
        payload = json.loads(sys.stdin.read())
        command = payload["tool_input"]["command"] if payload.get("tool_name") == "Bash" else ""
    except Exception:
        decide("deny", "git-guard: unreadable hook payload; denied (fails closed)")
        return 0
    if OBFUSCATED.search(command):
        decide("deny", "git-guard: $IFS or backslash-newline in a command is obfuscation; denied")
        return 0
    try:
        segs = parse(command)
    except ValueError:
        decide("deny", "git-guard: unbalanced quote; cannot tokenize, denied (fails closed)")
        return 0
    git_args = [seg[seg.index("git") + 1:] for seg in segs if "git" in seg]
    if any(pushes(seg) for seg in segs):
        if segs != [ALLOWED_PUSH]:
            decide("deny", f"git-guard: only the exact command `{' '.join(ALLOWED_PUSH)}` may push; "
                   "no force push, no wrapper shell, no other remote or ref, and `factory` is never pushed (AGENTS.md, Git and branches)")
        return 0
    for sub, hits, reason in ASK:
        if any(sub in a and hits(a[a.index(sub) + 1:]) for a in git_args):
            decide("ask", f"git-guard: {reason}; confirm before running")
            return 0
    if any("commit" in a for a in git_args):
        # TODO(gates): once the review gate writes .claude/.gate/PASSED, deny a commit without it
        # (mechanics research, section 4.5 route B) instead of logging.
        project_dir = os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd()
        log_dir = os.path.join(project_dir, ".claude", ".curate")
        os.makedirs(log_dir, exist_ok=True)
        with open(os.path.join(log_dir, "git-guard.log"), "a", encoding="utf-8") as log:
            log.write(json.dumps({"ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                                  "allowed": "commit", "command": command}) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
