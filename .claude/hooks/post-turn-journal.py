#!/usr/bin/env python3
"""AgentQuilt Stop hook — journal substantial turns.

Cheap (no LLM), best-effort, non-blocking. Output is consumed by /self-curate.
Writes one JSONL line per substantial turn to .claude/.curate/journal.jsonl.

Smoke test: printf '%s' '{"stop_hook_active":true}' | python3 .claude/hooks/post-turn-journal.py; echo $?   # 0, no journal line

Duplicate suppression (run from the repo root; scratch project dir, threshold raised so nothing spawns):
  d=$(mktemp -d); e='{"message":{"role":"assistant","content":[{"type":"tool_use","name":"Edit","input":{}}]}}'
  p=$(printf '{"session_id":"s","transcript_path":"%s"}' "$d/t.jsonl"); echo "$e" > "$d/t.jsonl"
  for i in 1 2; do printf '%s' "$p" | CLAUDE_PROJECT_DIR="$d" AGENTQUILT_CURATE_THRESHOLD=9999 python3 .claude/hooks/post-turn-journal.py; done
  wc -l < "$d/.claude/.curate/journal.jsonl"   # 1: the second Stop counted the same transcript lines
  echo "${e/Edit/Write}" > "$d/t.jsonl"; printf '%s' "$p" | CLAUDE_PROJECT_DIR="$d" AGENTQUILT_CURATE_THRESHOLD=9999 python3 .claude/hooks/post-turn-journal.py
  wc -l < "$d/.claude/.curate/journal.jsonl"   # 2: same totals, different activity — the window moved
"""
from __future__ import annotations

import fcntl
import hashlib
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

PROJECT_DIR = Path(
    os.environ.get("CLAUDE_PROJECT_DIR") or Path(__file__).resolve().parents[2]
)
CURATE_DIR = PROJECT_DIR / ".claude" / ".curate"
JOURNAL = CURATE_DIR / "journal.jsonl"
TRANSCRIPT_TAIL_LINES = 300

EDIT_TOOLS = {"Edit", "Write", "MultiEdit", "NotebookEdit"}
TEST_RE = re.compile(
    r"\b(pytest|ruff|pyright|mypy|npm\s+(?:run\s+)?(?:test|lint)|tsc\s+-b)\b"
)
GIT_RE = re.compile(r"\bgit\s+(commit|push|reset|checkout|merge|rebase)\b")
# Corrections are counted only; /self-curate reads the transcript and files the lesson as a suggestion.
CORRECTION_RE = re.compile(
    r"\b(no|stop|don'?t|wrong|incorrect|undo|that's not)\b", re.IGNORECASE
)


def _duplicate_of_last(entry: dict) -> bool:
    """Same activity signature as this session's last journal line: a re-fired Stop.

    Equal counter totals would not be proof — the rolling window can admit new
    activity while old activity scrolls out at the same totals. Best-effort like the
    rest of the file: an unreadable, corrupt, unsigned or just-rotated journal
    re-admits one duplicate.
    """
    try:
        with open(JOURNAL, "r", encoding="utf-8") as f:
            for line in reversed(f.readlines()):
                prev = json.loads(line)
                if prev.get("session") == entry["session"]:
                    return prev.get("sig") == entry["sig"]
    except Exception:
        pass
    return False


def main() -> int:
    try:
        raw = sys.stdin.read()
        payload = json.loads(raw) if raw.strip() else {}
    except Exception:
        return 0

    if payload.get("stop_hook_active") is True:
        return 0

    transcript = payload.get("transcript_path") or ""
    session = payload.get("session_id") or ""
    if not transcript or not Path(transcript).is_file():
        return 0

    try:
        with open(transcript, "r", encoding="utf-8", errors="replace") as f:
            lines = f.readlines()[-TRANSCRIPT_TAIL_LINES:]
    except Exception:
        return 0

    edits = test_runs = git_cmds = corrections = 0
    # Signature over the raw transcript lines that were counted, in order: it changes
    # whenever activity is added, removed or scrolled out of the window above, which
    # equal totals alone would miss.
    sig = hashlib.sha1(usedforsecurity=False)
    for line in lines:
        try:
            obj = json.loads(line)
        except Exception:
            continue
        msg = obj.get("message") or obj
        if not isinstance(msg, dict):
            continue
        content = msg.get("content")
        role = msg.get("role")
        before = (edits, test_runs, git_cmds, corrections)
        if isinstance(content, list):
            for block in content:
                if not isinstance(block, dict):
                    continue
                btype = block.get("type")
                if btype == "tool_use":
                    name = block.get("name", "")
                    if name in EDIT_TOOLS:
                        edits += 1
                    elif name == "Bash":
                        cmd = (block.get("input") or {}).get("command", "") or ""
                        if TEST_RE.search(cmd):
                            test_runs += 1
                        if GIT_RE.search(cmd):
                            git_cmds += 1
                elif btype == "text" and role == "user":
                    if CORRECTION_RE.search(block.get("text", "") or ""):
                        corrections += 1
        if (edits, test_runs, git_cmds, corrections) != before:
            sig.update(line.encode("utf-8", "replace"))

    if not (edits or test_runs or git_cmds or corrections):
        return 0

    # A curate lane's own turn is neither journaled nor counted.
    if os.environ.get("CLAUDE_SELF_CURATE_RUNNING") == "1":
        return 0

    # Best-effort.
    git_dirty = 0
    try:
        out = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=str(PROJECT_DIR),
            capture_output=True,
            text=True,
            timeout=2,
        )
        git_dirty = sum(1 for ln in out.stdout.splitlines() if ln.strip())
    except Exception:
        pass

    entry = {
        "ts": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "session": session,
        "edits": edits,
        "test_runs": test_runs,
        "git_cmds": git_cmds,
        "corrections": corrections,
        "git_dirty_files": git_dirty,
        "sig": sig.hexdigest(),
        "transcript": transcript,
    }
    try:
        CURATE_DIR.mkdir(parents=True, exist_ok=True)
        # Same lock as the /self-curate rotation (step 7), so an append never lands between its grep and mv.
        with open(CURATE_DIR / "journal.lock", "w") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            # Only the append is skipped; the threshold path below still runs, so a
            # duplicate Stop event can still fire a curate that is already due.
            if not _duplicate_of_last(entry):
                with open(JOURNAL, "a", encoding="utf-8") as f:
                    f.write(json.dumps(entry) + "\n")
    except Exception:
        pass

    # Threshold-driven auto-curate.
    threshold = int(os.environ.get("AGENTQUILT_CURATE_THRESHOLD", "15"))
    try:
        with open(JOURNAL, "r", encoding="utf-8") as f:
            count = sum(1 for ln in f if ln.strip())
    except Exception:
        return 0
    if count < threshold:
        return 0

    # Cooldown: don't fire a threshold curate within 60 min of the last
    # successful curate (SessionEnd/PreCompact curates are exempt — they run
    # via run-curate.sh directly). Journal keeps accumulating meanwhile.
    cooldown = int(os.environ.get("AGENTQUILT_CURATE_COOLDOWN_SECONDS", "3600"))
    last_file = CURATE_DIR / "last_curate.txt"
    try:
        last_ts = datetime.strptime(
            last_file.read_text().strip(), "%Y-%m-%dT%H:%M:%SZ"
        ).replace(tzinfo=timezone.utc)
        if (datetime.now(timezone.utc) - last_ts).total_seconds() < cooldown:
            return 0
    except Exception:
        pass  # no/unparseable last_curate.txt → no cooldown

    runner = PROJECT_DIR / ".claude" / "hooks" / "run-curate.sh"
    if not runner.is_file():
        return 0
    try:
        subprocess.Popen(
            ["bash", str(runner), "threshold"],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
            cwd=str(PROJECT_DIR),
            env={**os.environ, "CLAUDE_PROJECT_DIR": str(PROJECT_DIR)},
        )
    except Exception:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
