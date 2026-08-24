#!/usr/bin/env bash
# Provenance scrub at the sink. Usage: scrub.sh [path ...]   (default: the staged content of the current checkout)
# Reads the pre-tag grep pattern from the vault at run time (never embedded here); prints hits as file:line and
# exits 1 on any hit, 2 when the pattern, a named path or the grep itself fails. Then prints the by-eye read list.
# Smoke: a file holding one listed word -> one hit, exit 1;  scrub.sh REVIEW.md -> 0 hits, exit 0
set -euo pipefail
V=${V:-$(dirname "$(git rev-parse --path-format=absolute --git-common-dir)")/../AgentQuilt-Vault}
src="$V/30-research/2026-08-23-release-1-compliance.md"
pattern=$(grep -o 'pre-tag grep gate (`[^`]*`)' "$src" | sed 's/^[^`]*`//; s/`)$//')
[ -n "$pattern" ] || { echo "scrub-gate: pattern not found in $src" >&2; exit 2; }
for f in "$@"; do [ -f "$f" ] && [ -r "$f" ] || { echo "scrub-gate: cannot read $f" >&2; exit 2; }; done
rc=0
if [ $# -eq 0 ]; then hits=$(git grep -nEH --cached -e "$pattern") || rc=$?; scope="the staged tree"
else hits=$(grep -nEH -e "$pattern" -- "$@") || rc=$?; scope="$# file(s)"; fi
[ "$rc" -le 1 ] || { echo "scrub-gate: grep failed (exit $rc)" >&2; exit 2; }
if [ -n "$hits" ]; then printf '%s\n' "$hits"; echo "scrub-gate: $(printf '%s\n' "$hits" | wc -l) hit(s); nothing crosses"; exit 1; fi
echo "scrub-gate: 0 hits in $scope"
echo "Read by eye (public-copy register, $V/30-research/2026-08-23-release-1-ceo.md section 3 item 3):"
grep -o '^   | [^|]*|' "$V/30-research/2026-08-23-release-1-ceo.md" | sed 's/^   | *//; s/ *|$//' | grep -v '^word'
