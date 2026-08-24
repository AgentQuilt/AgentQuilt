#!/usr/bin/env bash
# Spawn /self-curate as a detached, async subprocess.
# Called by Stop (threshold), SessionEnd, PreCompact hooks, or manually.
#
# Args:
#   $1  trigger reason: threshold | sessionend | compact | manual
#
# Stdin (optional): hook JSON payload — if present, the `reason` field is
# appended to the log filename for traceability (e.g. SessionEnd → "clear").
#
# Recursion-guarded via CLAUDE_SELF_CURATE_RUNNING. Single-flight via a
# RUNNING flag file (treated as stale after 15 minutes). Safe to call from
# any hook; never blocks the caller.
#
# Smoke test: CLAUDE_PROJECT_DIR=$PWD bash .claude/hooks/run-curate.sh sessionend </dev/null; echo $?   # 0, no spawn when the journal is empty

set -uo pipefail

if [ "${CLAUDE_SELF_CURATE_RUNNING:-0}" = "1" ]; then
  exit 0
fi

REASON="${1:-manual}"
PROJECT_DIR="${CLAUDE_PROJECT_DIR:-$(pwd)}"
CURATE_DIR="$PROJECT_DIR/.claude/.curate"
LOG_DIR="$CURATE_DIR/logs"
RUNNING_FLAG="$CURATE_DIR/RUNNING"

mkdir -p "$LOG_DIR" 2>/dev/null || true

# Optional: read stdin JSON to extract specific reason (e.g. SessionEnd
# distinguishes clear / exit / logout / prompt_input_exit).
if [ ! -t 0 ]; then
  STDIN=$(cat 2>/dev/null || true)
  if [ -n "$STDIN" ]; then
    SUB=$(printf '%s' "$STDIN" | python3 -c "
import json, sys
try:
    d = json.loads(sys.stdin.read() or '{}')
    print(d.get('reason') or d.get('trigger') or '')
except Exception:
    pass
" 2>/dev/null || true)
    if [ -n "$SUB" ]; then
      REASON="${REASON}-${SUB}"
    fi
  fi
fi

# SessionEnd guard: don't spawn a headless claude just to discover there is
# nothing to curate. An empty/missing journal means no substantial turns were
# recorded since the last curate — skip. (PreCompact/threshold/manual triggers
# are exempt: compact is rare and about-to-lose-context, threshold implies a
# non-empty journal.)
case "$REASON" in
  sessionend*)
    if [ ! -s "$CURATE_DIR/journal.jsonl" ]; then
      exit 0
    fi
    ;;
esac

# Single-flight guard: skip if a curate is already running (≤ 15 min old).
if [ -f "$RUNNING_FLAG" ]; then
  if command -v stat >/dev/null 2>&1; then
    MTIME=$(stat -f %m "$RUNNING_FLAG" 2>/dev/null || stat -c %Y "$RUNNING_FLAG" 2>/dev/null || echo 0)
    AGE=$(( $(date +%s) - MTIME ))
    if [ "$AGE" -lt 900 ]; then
      exit 0
    fi
  fi
  rm -f "$RUNNING_FLAG" 2>/dev/null || true
fi

CLAUDE_BIN="$(command -v claude || true)"
if [ -z "$CLAUDE_BIN" ]; then
  exit 0
fi

TS=$(date -u +"%Y%m%dT%H%M%SZ")
LOG="$LOG_DIR/curate-${TS}-${REASON}.log"

touch "$RUNNING_FLAG"

# Detached background subprocess. Inherits CLAUDE_SELF_CURATE_RUNNING=1 so
# its own Stop/SessionEnd/PreCompact hooks short-circuit without recursing.
(
  trap 'rm -f "$RUNNING_FLAG"' EXIT
  cd "$PROJECT_DIR" 2>/dev/null || exit 0
  CLAUDE_SELF_CURATE_RUNNING=1 \
    "$CLAUDE_BIN" \
      --print "/self-curate (triggered by: ${REASON})" \
      --model "${AGENTQUILT_CURATE_MODEL:-claude-opus-5}" \
      --permission-mode bypassPermissions \
      --output-format text \
      > "$LOG" 2>&1
) </dev/null >/dev/null 2>&1 &

disown 2>/dev/null || true
exit 0
