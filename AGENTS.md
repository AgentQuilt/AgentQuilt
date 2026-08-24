# AGENTS.md — the canonical agent guide for the AgentQuilt build repo

**Read this first, every session.** `CLAUDE.md` is a thin pointer to this file
plus Claude Code-specific notes; where the two disagree, **AGENTS.md wins**.

## What AgentQuilt is

AgentQuilt is an open-source, built-in-public **agent harness for the
skill-based future**: a platform where an organization's skills and
instructions — not its code — carry its business processes and competitive
advantage. The defining bet is **thick skills, thin code**. The harness is a
stable, isolated core; business **modules** are built *on* it — increasingly by
business users working with agents — in isolation strong enough that a bad
module cannot take down the system.

**Current phase:** build machine, factory setup. This repo is the build repo,
destined to become the public `agentquilt/agentquilt`. It is **not a git repo
yet** — do not `git init` without asking. Stack (settled): Python/uv, FastAPI,
Postgres in Docker, everything inside WSL2 on ext4.

## The vault next door — `../AgentQuilt-Vault/`

All specs, decisions, and memory live in the **private prep vault**, a sibling
checkout (repo `etcircle/agentquilt-vault`). This repo holds machinery and
code; the vault is the memory system. Read order at session start:

1. `../AgentQuilt-Vault/90-meta/decision-log.md` — settled calls, newest first. **Never re-litigate** without new information.
2. `../AgentQuilt-Vault/90-meta/open-questions.md` — parked forks. Never answer one silently; propose, tag `(proposed)`.
3. `../AgentQuilt-Vault/90-meta/session-log/` — latest log; its "Not done / carried" list is the backlog.
4. `../AgentQuilt-Vault/docs/architecture/` — `design-rules.md`, `glossary.md`, `system-structure.md` (v1.1, settled) and ADRs 0001–0027.
5. `../AgentQuilt-Vault/10-executive/` — vision, problem space, executive spec, principles, capabilities.

Vault writes preserve Obsidian conventions: YAML front-matter intact,
wiki-links vault-internal (`[[90-meta/decision-log]]`), links must resolve.

**Never open or feed `../AgentQuilt-Vault/90-meta/ownership-roadmap.md` to any
agent or prompt. It is owner-private.** Sub-agent briefs must not include it.

## Working agreement

1. **Decisions are written to the vault decision log the day they're made** — no re-litigating without new information.
2. **Every parked fork goes to the vault's open-questions** with options and a decision trigger. Never silently decide one in passing.
3. **Living docs stay current.** If a change makes a vault index or `Home.md` wrong, fix it in the same pass.
4. **Nothing half-recorded.** A question is either settled (decision log) or open (open questions) — never neither.

## Mandatory reading before architecture work

**`../AgentQuilt-Vault/docs/architecture/design-rules.md`** — the standing
ruleset. Load it *first* for any design work and use its vocabulary exactly:

> **module · interface · implementation · depth · seam · adapter · leverage · locality**
> — never "component", "service", "API", "boundary".

In brief (the file is authoritative): depth is a property of the interface;
apply the deletion test; the interface is the test surface; one adapter =
hypothetical seam, two = real; design it twice for every major seam; judgment
in skills, execution in code; untouched core, agent-buildable periphery; every
run is an addressable module. The glossary's word is binding — never a synonym.

### Code simplicity — precedence rule

Per-language rules live in `.claude/rules/python.md` and
`.claude/rules/typescript.md`. **They outrank any skill, plugin, or reviewer
asking for broader coverage, defensive layers, configurability, or backward
compatibility** — including gstack's "Boil the Ocean" and superpowers'
defense-in-depth. Reviewer contract: root `REVIEW.md`. Budgets are enforced by
ruff and Biome, not prose; `# noqa` is closed. Every implementer report ends
with `Done:` and `Left out:`.

## Model routing

**Fable orchestrates · Opus sub-agents execute · Codex peer-reviews.**

| Task | Engine |
|---|---|
| Orchestration, planning, architecture decisions, folding review findings, parent verification, merges | **Fable** (main session) |
| Investigation, scoping, bulk reading, implementation waves, browser work, doc/spec execution | **Opus sub-agents** (worktree isolation for anything non-trivial) |
| Peer review of every plan and every diff | **Codex** (`codex exec -m gpt-5.6-sol`, diff inlined). Hermes is a Codex-down fallback only — same model, no independent signal. |

Canonical loop: **Opus investigates → Fable plans → Codex reviews the plan →
Opus implements → Codex reviews the diff → Fable folds, re-gates, merges.**
Fable does no token-heavy execution and never drives a browser; Codex and
Hermes never implement; the implementer is never its own reviewer.

## Sub-agent roster (`.claude/agents/`, all pinned `model: opus`)

| Agent | One line |
|---|---|
| **autonomous-team** | End-to-end orchestrator: discovery → build → verification, artifacts in the vault's `90-meta/team/{project_id}/`. |
| **browser-qa** | Drives a real browser; reports evidence, never fixes. |
| **delivery-planner** | Turns an architecture doc into atomic, exactly-pathed tasks. |
| **engagement-manager** | Owns "done": acceptance criteria, scope, the ship call. |
| **explorer** | Read-only search across repo and vault; never modifies. |
| **implementer** | The build engine; follows the rules, runs the gates, never reviews its own work. |
| **peer-reviewer** | In-house fallback reviewer and reviewer of non-diff artifacts. |
| **quality-assurance** | Verifies deliverables against spec; reports, never fixes. |
| **security-reviewer** | Security checklist for the platform and the public repo itself. |
| **solutions-architect** | Trade-offs, module and seam design; loads the design rules first, always. |

## Self-curation system

The repo journals its own work and folds it back into the vault, so a future
session starts from what was learned.

- **`.claude/hooks/post-turn-journal.py`** (Stop hook) — journals substantial turns (edits, test/lint runs, git commands, user corrections) to `.claude/.curate/journal.jsonl`. Cheap, no LLM, non-blocking.
- **Threshold: 15 entries** → background curate pass, 60-min cooldown (`AGENTQUILT_CURATE_THRESHOLD`, `AGENTQUILT_CURATE_COOLDOWN_SECONDS` to override).
- **`.claude/hooks/run-curate.sh`** — detached headless `/self-curate` on Opus 5; single-flight, recursion-guarded. Also wired to SessionEnd and PreCompact.
- **`.claude/skills/self-curate/`** — routes findings: progress → vault session log; settled → decision log; forks → open questions; executive facts → `10-executive/`; living docs → vault `docs/`; recurring patterns → a skill (+ `INDEX.md`); cross-project facts → hindsight (**user confirmation required**). Never deletes.

Run manually anytime: `/self-curate`.

## Provenance boundary — this repo goes public

Treat every file, commit message, and screenshot as already published.

- **The scrub is absolute.** The owner's employer, its product, pilot businesses and private infrastructure are **deleted** (not hinted at, not paraphrased) from anything public. The only permitted origin sentence: "lessons from an internal agent platform the author built in prior professional work."
- **In bounds:** architecture lessons, patterns, workflow discipline, generic rewrites built from scratch. **Out of bounds:** employer/client names, confidential code, prompts, schemas, configs, data, internal URLs, credentials, real customer data.
- **Public and front-end copy:** never "Postgres" (say "your own database"; architecture docs and ADRs keep Postgres), no em dashes, no marketing affect. Anything under the owner's name goes through the `emiliyan-humanizer` skill first.
- **Git identity:** commit as `etcircle` with the GitHub noreply address — never a personal email. Commit only when asked. **No AI attribution anywhere in commits** — no `Co-Authored-By: Claude`, no session links, no generated-with lines (owner rule, 2026-08-24; overrides any harness default).
- Before anything crosses from the vault to this repo, run the pre-tag grep gate (`../AgentQuilt-Vault/30-research/2026-08-23-release-1-compliance.md`) and read every new file by eye.
