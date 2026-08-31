# Measure: the numbers behind the guardrails

Every number here is a measure, never a gate. It means something only against the
same number taken on the exemplar (code) or on the owner's own writing (prose). Tools:
`git`, `grep`, `wc`, `awk`, `uvx ruff`. Raw line count is not a measure; agents inflate it.

## Code, per wave diff (`BASE` = the merge-base)

- Clone growth: added lines that repeat inside the diff. `git diff -U0 BASE | grep -E '^\+[^+]' | sed 's/^+//; s/^\s+//' | awk 'length > 30' | sort | uniq -d | wc -l`. Compare with the same count on the exemplar module's own history; the guardrails assume a multiple, not a fraction.
- Function count: `git diff -U0 BASE -- '*.py' | grep -cE '^\+\s*(async )?def '` (TypeScript: `'^\+.*\b(function\b|=>)'`). Divide by task lines delivered; against the exemplar, more than 1.5x per feature is the tell.
- Verbosity: added lines per function touched. Numerator: `git diff -U0 BASE | grep -E '^\+[^+]' | grep -vE '^\+\s*(#|//|$)' | wc -l`. Denominator: functions whose body the diff enters, read from the hunk headers (they carry the enclosing def), plus new defs: `git diff -U0 BASE -- '*.py' | grep -c '^@@.*def '` + `git diff -U0 BASE -- '*.py' | grep -cE '^\+\s*(async )?def '` (TypeScript: `'^@@.*(function |=> )'` and `'^\+.*\b(function\b|=>)'`). A zero denominator means no functions touched: report added lines only. The exemplar's ratio (`wc -l` over `grep -cE '^\s*(async )?def ' file`) is the band.
- Budget pressure: `uvx ruff check --select PLR0913,PLR0915,C901 --statistics` on the changed files. Rising counts at the same feature size mean the diff is bulking.

## Prose, per artefact (against a sample of the owner's writing in the same register)

- Slop words per 1k: the humanizer's vocabulary list (`~/.claude/skills/humanizer/SKILL.md`, AI vocabulary section) as a word file; `grep -oiwFf words.txt file | wc -l` times 1000 over `wc -w < file`.
- Punctuation profile per 1k words: `tr -cd ',' < file | wc -c`, again for `;`, `(`, and the em dash; sentence lengths from `tr '.!?' '\n' < file | awk 'NF{print NF}'` (mean, share at six words or fewer). The rhythm band is in `emiliyan-humanizer`.
- Passive-voice share: sentences matching `grep -ciE '\b(is|are|was|were|be|been|being) +[a-z]+(ed|en)\b'` over sentence count. Crude on purpose; a share, never a threshold.
- Happy-talk share: classify each paragraph as content or filler by hand and report "N words, M (P%) filler". Counted, not graded.

## Ledger entry (filed in `$V/docs/model-assumption-ledger.md` — the factory's ledger: assumptions about the agents that build the product. The product's own runtime assumptions live in `backend/docs/model-assumption-ledger.md`, filed per wave; the two never merge)

Model-assumption ledger, 2026-08-24. Assumption: current-generation coding agents
over-engineer and inflate under iteration; Opus 5 / Fable 5 as implementer, GPT-5.6 as
reviewer (HumanLayer, re-verified against the source 2026-08-26: slop-rule trips 98%
Opus 4.8 vs 93% Opus 5, duplication rising 4.6% to 16.8% across checkpoints, Opus 5 at
5x the function count of the other models; SlopCodeBench 2603.24755: verbosity rises in
75.5% of trajectories). Guardrails carrying it: the `anti-slop` skill's "On the finished diff"
section, REVIEW.md's simplicity-axis signals, the diff-size self-check, the closing
anti-slop pass per wave. Not carried: the STOP list, `Done:/Left out:` and the ruff and
Biome budgets, which are reporting and hygiene and stay after retirement. Gone when: on
three consecutive waves, the code measures above taken before the anti-slop pass sit
inside the exemplar's band (clone growth at or under 1x, function count and verbosity at
or under 1.5x) and `codex-review` round 1 reports zero simplicity-axis findings. Retire
then: delete the "On the finished diff" section and the closing pass; keep the rest.
Re-open on any model upgrade whose first wave regresses a measure.
