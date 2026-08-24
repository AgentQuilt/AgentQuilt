#!/usr/bin/env bash
# Codex peer review with the fail-closed gate. Usage:
#   review.sh diff <wave> [base=factory] [round=1]   review the merge-base diff of the current checkout
#   review.sh plan <wave> <file> [round=1]           review a plan file
#   review.sh check <out.md>                         does the review still bind to this working tree?
# Reads temp/<wave>_review_context.md when present.
set -euo pipefail
root=$(git rev-parse --show-toplevel); cd "$root"
tpl="$root/.claude/skills/codex-review/references/prompt-template.md"

tree_hash() {  # working tree content, tracked plus untracked
  local idx; idx=$(mktemp); rm -f "$idx"; GIT_INDEX_FILE=$idx git read-tree HEAD; GIT_INDEX_FILE=$idx git add -A
  GIT_INDEX_FILE=$idx git write-tree; rm -f "$idx"
}
state_hash() {  # plus the plan file, which lives outside the tree
  local t; t=$(tree_hash); [ -z "${plan:-}" ] || t="$t+$(sha256sum "$plan" | cut -c1-40)"; echo "$t"
}
render() {  # $1 template, $2 artefact file, $3 context file, $4 kind (diff|plan); @@X@@ placeholders
  local calib; calib=$(awk '/^## Review-prompt calibration/{f=1;next} f&&/^> /{sub(/^> /,"");print;exit}' AGENTS.md)
  while IFS= read -r line; do case "$line" in
    @@CONTEXT@@) [ -f "$3" ] && cat "$3" || echo "(no context file)";;
    @@ARTEFACT@@) cat "$2";; @@CALIBRATION@@) printf '%s\n' "$calib";;
    @@RULES@@) cat REVIEW.md;; *) printf '%s\n' "${line//@@KIND@@/$4}";;
  esac; done < "$1"
}
gate() {  # $1 output file, $2 codex exit code
  if [ "$2" -ne 0 ]; then echo "VERDICT: FAIL (codex exit $2; see error taxonomy in SKILL.md)"
  elif [ ! -s "$1" ]; then echo "VERDICT: FAIL (empty output)"
  elif ! grep -Eq '^P[123] |^NO FINDINGS$' "$1" || ! grep -Eq '^VERDICT: (PASS|FAIL)' "$1"; then
    echo "VERDICT: FAIL (verification failure: needs a severity tag or NO FINDINGS, plus a verdict line)"
  elif grep -Eq '^P1 |^VERDICT: FAIL' "$1"; then echo "VERDICT: FAIL (P1 present, or the reviewer said FAIL)"
  else echo "VERDICT: PASS"; fi
}

mode=${1:-}; wave=${2:-}
case "$mode" in
  diff) base=${3:-factory}; round=${4:-1}; artefact=$(mktemp)
        untracked=$(git ls-files --others --exclude-standard)
        [ -z "$untracked" ] || { printf 'untracked files present; commit or ignore them first:\n%s\n' "$untracked" >&2; exit 2; }
        git diff "$(git merge-base "$base" HEAD)" > "$artefact"
        [ -s "$artefact" ] || { echo "nothing to review: empty diff against merge-base of $base" >&2; exit 2; };;
  plan) artefact=${3:?plan file}; plan=$artefact; round=${4:-1};;
  check) hash=$(sed -n 's/^tree: //p' "${wave:?output file}"); plan=$(sed -n 's/^plan: //p' "$wave"); now=$(state_hash)
         [ "$hash" = "$now" ] && echo "binds: tree $now unchanged" || { echo "stale: reviewed $hash, tree now $now"; exit 1; };;
  *) sed -n '2,6p' "$0"; exit 2;;
esac
[ "$mode" = check ] && exit 0
command -v codex > /dev/null || { echo "codex not on PATH" >&2; exit 2; }
mkdir -p temp; prompt="temp/${wave:?wave}_${mode}_review_prompt_r${round}.txt"; out="temp/${wave}_${mode}_review_r${round}.md"
render "$tpl" "$artefact" "temp/${wave}_review_context.md" "$mode" > "$prompt"; stamp=$(state_hash)  # hashed before the review, so later edits read as stale
rc=0; timeout 560 codex exec -m gpt-5.6-sol --skip-git-repo-check -c 'sandbox_mode="read-only"' -o "$out" - < "$prompt" > /dev/null 2> "$out.log" || rc=$?
[ -f "$out" ] || : > "$out"
printf '\n--- reviewer output (%s), verbatim ---\n' "$out"; cat "$out"
printf -- '\n--- gate ---\n%s\ntree: %s\n%s' "$(gate "$out" "$rc")" "$stamp" "${plan:+plan: $plan
}" | tee -a "$out"
