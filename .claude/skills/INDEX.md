# Skills index

Catalog of the project skills in `.claude/skills/<name>/SKILL.md` plus the global skills the factory depends on (marked global). Maintained by
`skill-author`; `self-curate` only flags a stale line. Sort alphabetical; one line per skill.

- anti-slop — The implementer's self-check on its own diff before the report: the architecture checks by name, stop conditions, `Done:`/`Left out:`; `references/` hold the pattern catalogue, the prose routing to the humanizer chain, the measures and the ledger entry. Implementer-fired on its own diff, plus the closing anti-slop pass each wave (Fable); never on prose. [touched: 2026-08-24]
- catchup — Re-read AGENTS.md, decision-log head, open questions, latest session log and the branch diff; report, change nothing. Fable-fired at session start or after compaction. [touched: 2026-08-24]
- codex-review — Codex peer review of a diff or plan through the fail-closed gate (`scripts/review.sh`); fold discipline, stop rule, error taxonomy, arbitration. Fable-fired after every wave. [touched: 2026-08-24]
- curate-fold — Decide each open entry in `$V/90-meta/suggestions.md` (accept / reject / defer, one sentence, marked in place) and route accepted factory changes into a wave. Fable-fired at a phase boundary. [touched: 2026-08-24]
- emiliyan-humanizer (global, `~/.claude/skills/`) — Draft or rewrite anything published under the owner's name in his measured voice, then run `humanizer` with his documented exceptions; ends with `Done:` / `Kept as his:`. The vault's `50-bootstrap/owner-voice-profile.md` is canonical. [touched: 2026-08-23]
- frontend-design — Surface procedure under `frontend/`: tokens and catalog first, reuse-before-create per visual object, one exemplar, copy lines, accessibility floor, hand-off to `browser-qa`. Implementer-fired; dormant until a surface exists. [touched: 2026-08-24]
- handoff — Save a half-page handoff to `$V/90-meta/handoffs/` (branch, Verified, one Next command) or resume from the latest with a branch-mismatch check. Fable-fired at a session boundary. [touched: 2026-08-24]
- humanizer (global, `~/.claude/skills/`) — Remove signs of AI-generated writing from text; the second step of the `emiliyan-humanizer` chain. [touched: 2026-08-24]
- land-gate — Pre-merge evidence gate: fresh output only, rebased onto factory before gates, review still binds (`codex-review` check), docs match the diff, non-destructive worktree cleanup. Fable-fired after codex-review PASS; dormant until code. [touched: 2026-08-24]
- plan-gate — Premises, alternatives, leverage pass, pass/fail criteria, executability score; runs on every plan before `codex-review`. Fable-fired. [touched: 2026-08-24]
- root-cause — Diagnosis before fix: red command, minimal reproduction, ranked hypotheses, tagged logs, regression test at the seam, three-strike and five-file stops. Implementer-fired on bugs; dormant until code. [touched: 2026-08-24]
- scrub-gate — Grep files at the sink for provenance leaks with the vault's pre-tag pattern (`scripts/scrub.sh`, exit 1 on hits) and print the by-eye read list. Fable- or owner-fired before any export. [touched: 2026-08-24]
- self-curate — Record what the session learned in the vault memory zones (session log, decision log, open questions, cross-project memory), flag stale docs, file proposed factory changes as suggestions; edits no factory file. Triggers on "wrap up"/"save this"/settled decisions/journal at the AGENTS.md threshold. Headless model: Opus 5. [touched: 2026-08-24]
- skill-author — House procedure for creating or changing a project skill: reuse check, shadowing check, budgets, staged draft, script smoke, INDEX line. Use whenever a skill is created or its frontmatter changes. [touched: 2026-08-24]
