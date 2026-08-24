---
name: self-curate
description: Route what this session learned into the vault's memory zones (session log, decision log, open questions, executive notes, living docs, skills, hindsight). Trigger on "wrap up", "save this", "remember this", "update the decision log/open questions"; after a decision settles or a correction worth keeping; or when the curate journal has 5+ unprocessed entries.
user-invocable: true
disable-model-invocation: false
---

# /self-curate — automate the session-end pass

Turns the "session end" habit into one reliable pass instead of an aspirational
checklist. AgentQuilt's zones already exist (see `AGENTS.md`); this skill *uses*
them.

## What this skill is and isn't

- **Is**: a mostly-deterministic reflection that processes work since the last curate and writes to existing zones.
- **Is not**: a memory system. The vault is the memory system.

## Procedure

### 1. Read the inputs (parallel)

- `cat .claude/.curate/journal.jsonl` — substantial turns since last curate (may be empty)
- `cat .claude/.curate/last_curate.txt` (if exists) — timestamp of last successful curate
- `git status --porcelain` and `git diff --stat` — **only if this checkout is a git repo**; the vault phase has no git, so a failure here is expected and not an error
- Today's `../AgentQuilt-Vault/90-meta/session-log/YYYY-MM-DD.md` if it exists
- `head -40 ../AgentQuilt-Vault/90-meta/decision-log.md` and `head -40 ../AgentQuilt-Vault/90-meta/open-questions.md`
- `../AgentQuilt-Vault/Home.md` — the map of content, so you route into the structure that actually exists

If the journal is empty AND (no git, or working tree clean and no new commits
since last curate) → output "Nothing to curate." and stop.

### 2. Categorize what happened

For each piece of work, classify as exactly **one** of:

- **Session-log only** — routine progress, what was tried, what got read, file lists. → append to `../AgentQuilt-Vault/90-meta/session-log/YYYY-MM-DD.md` (create the file and the directory if missing).
- **Durable decision** — a question that got *settled*, with a reason. → prepend an entry to `../AgentQuilt-Vault/90-meta/decision-log.md` (newest first; format: `**YYYY-MM-DD — decision — why — supersedes (if any)**`). Leave a one-line breadcrumb in the session log; do not duplicate the body. If it supersedes an earlier entry, say so explicitly in the new entry — never edit the old one out.
- **New open question / parked disagreement** — something surfaced that is genuinely undecided. → add a `- [ ]` bullet to `../AgentQuilt-Vault/90-meta/open-questions.md`, phrased so a future session can decide it (state the options, the leading hypothesis if any, and what would trigger the decision).
- **Open question answered** — → move it: write the decision to `../AgentQuilt-Vault/90-meta/decision-log.md`, then check the box or remove the bullet in `../AgentQuilt-Vault/90-meta/open-questions.md` with a pointer to the decision date. Never silently drop it.
- **Executive-level fact or refinement** — changes what the product *is*, who it's for, its principles or capabilities. → edit the right `../AgentQuilt-Vault/10-executive/*.md` note (`01-vision`, `02-problem-space`, `03-executive-spec`, `04-brand-and-channel`, `05-architecture-principles`, `06-core-capabilities`, `07-design-doc-*`). Keep the note's existing voice and front-matter `status:` line honest — if a draft became settled, say so.
- **Living-doc change** — user-facing behaviour, architecture record, or sequencing firmed up. → update the relevant index: `../AgentQuilt-Vault/docs/user/index.md`, `../AgentQuilt-Vault/docs/architecture/index.md` (+ `../AgentQuilt-Vault/docs/architecture/design-rules.md` when a *standing rule* changed), `../AgentQuilt-Vault/docs/roadmap/index.md`. These files carry a "keep current" contract — honour it.
- **Code-repo structural change** *(activates when the code repo exists)* — modules, interfaces, seams, or dependencies changed. → update the module's own doc and any code-side index, and record the architectural decision as an ADR under `docs/adr/` per the executive principles.
- **Reusable workflow / pattern** — class-level, generalizable across sessions. → handled in Step 3 below (skill evaluation).
- **Cross-project / infra / homelab fact** — visible from other repos too. → `hindsight remember "…" --tag agentquilt` (see the invariant in Step 5 — **confirm with the user first**). Skip secrets/tokens/credentials.
- **Inbox residue** — a brain dump in `../AgentQuilt-Vault/00-inbox/` that has now been merged into its proper note. → delete the inbox file, per the working agreement in `../AgentQuilt-Vault/Home.md`.
- **Discard** — speculative, one-off, or already documented.

**Public-repo filter (applies to every zone).** AgentQuilt is destined to be a
public open-source repo. Never write into the vault: employer or client names,
confidential product internals, internal URLs or hostnames, credentials, or
anything copied verbatim from a private codebase. Architecture *lessons* are
in-bounds; provenance detail is not.

### 3. Evaluate skills (always — recursive self-improvement)

This step runs every curate, not only when triggered by a correction. The goal
is to capture recurring patterns from main-agent operations so future runs are
cheaper and more consistent.

For each pattern observed in this batch of turns, decide one of:

- **Patch existing skill** — there's already a `.claude/skills/<name>/SKILL.md` whose scope covers this pattern, and the new lesson is a concrete refinement (gotcha, edge case, sharper rule, an exception). Append a labeled subsection (`## <topic>`); never rewrite the body.
- **Create new skill** — pattern is class-level, recurred in ≥2 sessions (or is obviously generalizable from this one), and no existing skill is a sensible umbrella. New skill goes at `.claude/skills/<kebab-name>/SKILL.md` with the standard frontmatter (`name`, `description`, `user-invocable`, `disable-model-invocation`). The `description:` must include enough trigger keywords for Claude to auto-invoke it later — but stay brief (2–3 sentences: what + when to trigger); procedure detail belongs in the body, which only loads on invocation.
- **No skill change** — pattern is one-off, ambiguous, or already covered by `AGENTS.md` / `../AgentQuilt-Vault/docs/architecture/design-rules.md` / an existing skill.

Triggers that warrant patch-or-create (not exhaustive — use judgment):
- User correction or explicit approval of a non-obvious approach.
- A new rule stated outright ("from now on", "always", "never").
- The main agent repeated the same recovery sequence after a class of failure.
- A workflow the agent re-derived from scratch that has a clear, repeatable shape.

Conservative defaults still apply:
- No skill for a single-session fix tied to one file / one error string / one codename.
- No skill duplicating `AGENTS.md` guidance; reference it instead.
- When in doubt → log a "candidate skill" line in today's session log rather than creating prematurely. If the same candidate appears in a future curate, promote it.

After any skill patch/create, update `.claude/skills/INDEX.md` so the catalog
stays discoverable. Format per line:

```
- <skill-name> — <one-line description from frontmatter> [touched: YYYY-MM-DD]
```

Keep entries sorted alphabetically. Create the index file if it doesn't exist.

### 4. Apply changes

- Prefer `Edit` over `Write` for existing files.
- **Path convention:** paths in this skill are relative to the build repo root (`AgentQuilt/`); the vault is the sibling `../AgentQuilt-Vault/`. But wiki-links *written into vault notes* are vault-internal — `[[90-meta/decision-log]]`, never `[[../AgentQuilt-Vault/...]]` — so they resolve in Obsidian.
- Preserve Obsidian conventions: YAML front-matter stays intact, wiki-links use the existing `[[path/to/note|Label]]` shape, and any note you link to must actually exist.
- For `../AgentQuilt-Vault/90-meta/decision-log.md`: newest entry goes at the top of the list; one entry per decision; never reorder or reword existing entries.
- For `../AgentQuilt-Vault/10-executive/*.md`: edit only the section that actually changed. Do not rewrite unrelated prose.
- For skill patches: add a labeled subsection (`## <topic>`); never rewrite the skill body.
- For hindsight writes: one `hindsight remember "<fact>" --tag agentquilt` per fact, after user confirmation. Add extra `--tag` flags for cross-cutting topics (`--tag infra`, `--tag pattern`). Write only durable, non-secret, cross-project facts — project-internal facts belong in the vault, not hindsight.

### 5. Invariants (non-negotiable)

- Do **not** delete content from `../AgentQuilt-Vault/90-meta/decision-log.md`, `../AgentQuilt-Vault/90-meta/open-questions.md`, `../AgentQuilt-Vault/10-executive/*`, `docs/*`, or any skill. Append, edit-in-place, or move. Superseded content is marked superseded, never removed. (The one sanctioned deletion is an `../AgentQuilt-Vault/00-inbox/` file whose content has been merged — that is the working agreement in `../AgentQuilt-Vault/Home.md`.)
- Do **not** create a new skill for a one-session fix or a session artifact (a PR number, a feature codename, a specific error string). Class-level umbrellas only.
- **Hindsight writes require user confirmation** in this project — there is no standing approval here. Batch the proposals and ask once, at Step 4.
- Do **not** write secrets, tokens, `.env` values, or anything credential-shaped to any zone.
- Do **not** write employer/client-identifying material to any zone (public-repo filter, Step 2).
- If today's session log doesn't exist, create it; otherwise append.
- Irreversible cross-project actions (deleting hindsight memories, deleting/renaming skills, force-pushing) require explicit confirmation in *this* turn.

### 6. Enforce the decision-log size budget (400 lines)

After applying changes, run `wc -l ../AgentQuilt-Vault/90-meta/decision-log.md`. If it exceeds
**400 lines**, compact before stopping:

1. Identify the **oldest 20%** of entries — by date, since the log is newest-first (so: the entries at the bottom).
2. Append them verbatim to `../AgentQuilt-Vault/90-meta/archive/decision-log-<YYYY-MM>.md` (create the file if missing — same format as the log).
3. Replace the moved block with a single breadcrumb line:
   `- (archived: <one-line summary of the block, e.g. "Aug 2026 stack + framing decisions") → [[90-meta/archive/decision-log-<YYYY-MM>]]`
4. Re-check `wc -l`. If still > 400, repeat (next 20%) until under cap. After three rounds still over → stop and surface a warning in the report; manual review needed.

Compaction invariants:
- Never delete an entry; only **move** it.
- Never edit the *content* of moved entries while moving — they stay verbatim in the archive.
- Prefer archiving by topic-group when entries are tightly related, even if that means slightly more or fewer than 20%.
- The cap applies to `../AgentQuilt-Vault/90-meta/decision-log.md` only. Session logs and executive notes have their own bounds.

Also bound the journal archive: delete files in `.claude/.curate/archive/` older
than **30 days**.

### 7. Mark the journal as processed

```
mkdir -p .claude/.curate/archive
test -f .claude/.curate/journal.jsonl && \
  mv .claude/.curate/journal.jsonl ".claude/.curate/archive/journal-$(date -u +%Y%m%dT%H%M%SZ).jsonl"
date -u +"%Y-%m-%dT%H:%M:%SZ" > .claude/.curate/last_curate.txt
```

### 8. Report

Output a short summary in this exact shape:

```
Curated N turns since <last_curate_ts>.
- ../AgentQuilt-Vault/90-meta/session-log/YYYY-MM-DD.md: <one-line change>
- ../AgentQuilt-Vault/90-meta/decision-log.md: <N decisions added / no change>
- ../AgentQuilt-Vault/90-meta/open-questions.md: <N opened / N resolved / no change>
- ../AgentQuilt-Vault/10-executive/<note>.md: <one-line change / no change>
- docs/<area>/index.md: <one-line change / no change>
- 00-inbox: <N merged-and-deleted / no change>
- skill <name>: <patched / created / candidate logged / no change>
- skills/INDEX.md: <updated / no change>
- hindsight: <N facts proposed+confirmed / not used>
- decision-log size: <N lines> (cap 400) [+ "compacted: archived M entries" if applicable]
- discarded: <N items>
```

Done.

## Trigger heuristics

Run this skill (without being asked) when:
- User says "wrap up", "session end", "save this", "remember this", "update the decision log", "update open questions".
- A correction just landed and the underlying lesson is worth keeping.
- A decision just got settled in conversation — decisions are written down the day they're made (`../AgentQuilt-Vault/Home.md` working agreement).
- A multi-step task just finished and `.claude/.curate/journal.jsonl` has 5+ entries.

Do **not** run on:
- Single-turn lookups, read-only exploration, or planning conversations that settled nothing.

## Parallel-session journal hygiene

`.claude/.curate/journal.jsonl` and `.claude/.curate/last_curate.txt` are shared
across every session on the same checkout, including agent worktrees. If a
parallel session is active while a curate runs, the journal will contain foreign
entries and the rotate step can race a sibling curate.

- **Step 1 (read journal)** — after reading the journal, partition by `session:` (or transcript path). Only entries whose transcript points at *this* session count as work-to-summarize; foreign entries are context. If this session's own slice is empty AND nothing else changed since the last curate → output "Nothing to curate for this lane" (do not synthesize a summary from someone else's work).
- **Step 7 (rotate + re-stamp)** — capture the `last_curate.txt` value you read at start-of-run into a shell variable. After writing the new timestamp, re-read it: if it's older than the start-of-run stamp, a sibling raced you — re-stamp with the current UTC time and note the race in today's session log. Use `test -f` before `mv` so a sibling that already rotated doesn't cause a non-zero exit.

## Hook-spawned curate lanes

`run-curate.sh` fires from `PreCompact` and `SessionEnd`, so the curate usually
runs as its **own** Claude session with no journal entries of its own. Applying
"Parallel-session journal hygiene" literally would then abort it as *nothing to
curate for this lane* — wrong, because the whole point of that run is to curate
the session that triggered it.

Decide by lane type before applying the partition rule:

- **Hook-spawned lane** (no user turns of its own; the invocation carries `triggered by: compact-*` / `sessionend`): everything in the journal newer than `last_curate.txt` is work to summarise, foreign session ids included. The journal records counters only — never *what* happened — so read the triggering session's transcript at `~/.claude/projects/<project-slug>/<session-id>.jsonl`, filtering entries by `timestamp >= last_curate`.
- **In-session lane** (a user typed `/self-curate` in a session that did work): partition by `session:` as written above.

To learn your own session id: any Bash output large enough to be persisted names
it in the path (`…/projects/<slug>/<session-id>/tool-results/…`). Match journal
`session:` fields against that.

## Editing the factory tree while a wave is live

The build repo's checkout may be mid-wave — a worktree branch waiting to merge
into `factory`. A merge refuses to run when a file it touches has uncommitted
local changes, so a curate that patches a skill can block someone else's merge.

Before editing anything under `.claude/`, run
`git -C <build repo> diff --name-only factory...<wave-branch>` and stay off those
paths. `.claude/skills/INDEX.md` is the usual casualty — it is in nearly every
wave diff. If the index entry only needs a `[touched:]` date that is already
correct, skip it; otherwise note the deferred index edit in the session log and
in the report rather than dirtying the file.

## See also

- `references/routing.md` — quick routing cheat sheet
- `AGENTS.md` (project root) — the canonical agent guide; defines the zones this skill writes to
- `../AgentQuilt-Vault/Home.md` — map of content + the working agreement
