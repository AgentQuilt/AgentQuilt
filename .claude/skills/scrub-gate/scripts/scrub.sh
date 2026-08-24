#!/usr/bin/env bash
# Provenance scrub at the sink. Usage: scrub.sh [path ...]   (default: every tracked file of the current checkout)
# Reads the pre-tag grep pattern from the vault at run time (never embedded here); prints hits as file:line and
# exits 1 on any hit, 2 when the pattern cannot be read. Then prints the by-eye read list.
# Smoke: a file holding one listed word -> one hit, exit 1;  scrub.sh REVIEW.md -> 0 hits, exit 0
set -euo pipefail
V=${V:-$(dirname "$(git rev-parse --path-format=absolute --git-common-dir)")/../AgentQuilt-Vault}  # resolves from worktrees too
src="$V/30-research/2026-08-23-release-1-compliance.md"
pattern=$(grep -o 'pre-tag grep gate (`[^`]*`)' "$src" | sed 's/^[^`]*`//; s/`)$//')
[ -n "$pattern" ] || { echo "scrub-gate: pattern not found in $src" >&2; exit 2; }
if [ $# -eq 0 ]; then mapfile -t files < <(git ls-files); else files=("$@"); fi
hits=$(grep -nEH "$pattern" "${files[@]}" || true)
if [ -n "$hits" ]; then printf '%s\n' "$hits"; echo "scrub-gate: $(printf '%s\n' "$hits" | wc -l) hit(s); nothing crosses"; exit 1; fi
echo "scrub-gate: 0 hits in ${#files[@]} file(s)"
echo "Read by eye (public-copy register, $V/30-research/2026-08-23-release-1-ceo.md section 3 item 3):"
grep -o '^   | [^|]*|' "$V/30-research/2026-08-23-release-1-ceo.md" | sed 's/^   | *//; s/ *|$//' | grep -v '^word'
