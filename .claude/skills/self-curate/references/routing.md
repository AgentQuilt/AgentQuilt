# Routing cheat sheet — where does it go?

| Kind of finding | Destination |
|---|---|
| Routine progress, what was tried, what was read | `../AgentQuilt-Vault/90-meta/session-log/YYYY-MM-DD.md` |
| A question that got **settled**, with a why | `../AgentQuilt-Vault/90-meta/decision-log.md` (newest first) + session-log breadcrumb |
| Something genuinely undecided / a parked disagreement | `../AgentQuilt-Vault/90-meta/open-questions.md` (as `- [ ]`, with options + decision trigger) |
| An open question that just got answered | Decision → decision log; then tick/remove the bullet in open-questions with a pointer |
| Changes what the product *is*, who it's for, its principles | the right `../AgentQuilt-Vault/10-executive/*.md` note |
| A **standing architecture rule** changed | `../AgentQuilt-Vault/docs/architecture/design-rules.md` (+ note it in the decision log) |
| User-facing behaviour firmed up | `../AgentQuilt-Vault/docs/user/index.md` |
| Technical record / new architecture page | `../AgentQuilt-Vault/docs/architecture/index.md` |
| Sequencing / phases decided | `../AgentQuilt-Vault/docs/roadmap/index.md` |
| Module / interface / seam / dependency change *(once code exists)* | the module's own doc + an ADR in `docs/adr/` |
| Reusable class-level workflow | patch existing `.claude/skills/<name>/SKILL.md` (preferred) or create a new class-level skill |
| Cross-project / homelab / infra fact | `hindsight remember "…" --tag agentquilt` — **confirm with the user first** |
| An `../AgentQuilt-Vault/00-inbox/` dump that has now been merged | delete the inbox file (working agreement in `../AgentQuilt-Vault/Home.md`) |
| One-off task detail, speculative | discard |
| Secret, token, credential, `.env` value | NEVER |
| Employer/client name, confidential internals, internal URLs | NEVER — this repo goes public |

## Skill umbrella discipline

Before creating a new skill, ask: "could this be a labeled subsection under an
existing skill?" The default answer is yes. New skills are reserved for
genuinely class-level workflows, not session artifacts.

Three legitimate skill operations during /self-curate:

1. **Patch existing umbrella** — add a `## <topic>` subsection with the lesson.
2. **Create new umbrella** — only when no existing skill fits AND the pattern will recur across sessions.
3. **Demote to support file** — move narrow detail into `references/<topic>.md` under the umbrella, instead of inline in SKILL.md.

## Session log vs. decision log

| Question | Session log | Decision log |
|---|---|---|
| Will this matter in 2 weeks? | maybe | yes |
| Is it a list of things tried? | yes | no |
| Is it a decision with a "why"? | one line + pointer | full entry |
| Does it supersede an earlier call? | note it | yes — say what it supersedes |

When in doubt: write the body in the session log; add a decision-log entry only
if you can state the *settled* question and its reason in one sentence.

## Decision log vs. open questions

The two are a pair. Anything that arrives as a genuine fork in the road goes to
open-questions with its options; when it's resolved it *moves* to the decision
log and the open question is closed with a pointer. Neither file should ever
contain a half-decision that isn't traceable in the other.

## Substantiality (what the Stop hook journals)

The Stop hook treats a turn as substantial when the transcript shows any of:
- Edit / Write / MultiEdit / NotebookEdit tool calls
- Bash invoking `pytest`, `ruff`, `pyright`, `mypy`, `npm test|lint`, `tsc -b`
- Bash invoking `git commit|push|reset|checkout|merge|rebase`
- A user message containing a correction signal (`no`, `stop`, `don't`, `wrong`, `incorrect`, `undo`, `that's not`)

Read-only turns and pure planning turns are intentionally skipped — they don't
generate journal entries and don't need a curate pass. In the current vault
phase the edit signal is the one that fires; the test/git signals activate when
the code repo exists.
