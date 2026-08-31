---
name: lavish
description: Open a plan page for the owner's markup, poll his feedback, fold it, export the page once settled. Fable fires it for every plan page, never for a diff.
---

# lavish

The policy is in AGENTS.md (canonical loop and provenance boundary): the page is the plan, it lives in the gitignored `.lavish/`, `share` is never run, `export` is the only way out. This is the procedure that makes one page work. `$V` as defined in AGENTS.md.

## Procedure

1. Write the page at `.lavish/<name>.html`, self-contained: the style block and decision-card markup from the newest page in `.lavish/` (the design tokens, light and dark), no external assets. A decision is a card with native radios, the recommended option first and marked, and the five lines the owner expects (what you said, what we recommend, why, what we might be missing, cost if wrong). Done: the file opens in a browser without the server.
2. Gate before the owner sees it: `plan-gate`, then `codex-review` in plan mode. Done: the kicker line on the page carries the score, the dispatch count and the Codex round reached.
3. Open: `npx --no-install lavish-axi .lavish/<name>.html` from the repo root; the port and the allowed host come from `settings.local.json` (`LAVISH_AXI_PORT`, `LAVISH_AXI_ALLOWED_HOSTS`; the phone reaches the same session through the authenticated hostname in `$V/50-bootstrap/lavish-remote-access.md`). Done: the command prints `status: opened` and a session URL; give the owner the URL.
4. Poll: `npx --no-install lavish-axi poll .lavish/<name>.html` as a harness-tracked background job that wakes this agent (the Bash tool's background mode), or in the foreground; never under `nohup` or a bare `&`. Re-run it when it times out; feedback stays queued. Done: the poll output shows `status: feedback` and `prompts[N]`.
5. Fold every prompt in place: a card answer settles its decision (radio checked and disabled, `settled-mark`, an `outcome` block naming the owner's words); a question becomes a new card, never a silent answer; an idea outside the plan goes to `$V/90-meta/open-questions.md` tagged `(proposed)`. Re-run the poll with `--agent-reply "<what changed>"`. Done: every prompt uid has a change or a written reason.
6. Stop when `session_ended: true`: do not reopen; `--reopen` only on the owner's word. "I am ok with it" or "go" on the page is the green light. Done: the decisions are dated lines in `$V/90-meta/decision-log.md` the same day, and the open bullets they close are ticked.
7. Cross to the public repo only after the green light: grep the source page for the machine first — the account name, `$HOME`, absolute local paths, host and container names — and generalise the hits on the source (`scrub-gate` greps a word register and does not see these), then `npx --no-install lavish-axi export .lavish/<name>.html --out docs/plans/<slug>/index.html`, then `scrub-gate` on the exported files, then the by-eye read. A hit is fixed on the source page and re-exported, never on the export. Done: `scrub.sh` exits 0 on the files that cross and `docs/plans/index.md` lists the plan.

## Output

To the owner, after step 3: the session URL and the number of decisions on the page. After step 6: one line per decision, `D<n> — <settled how> — <where recorded>`.

## Limits

The poll returns only what the owner sends; layout warnings wait in his inbox until he queues them. The skill does not verify the page renders on a phone, and `lavish-axi` is a three-month-old tool pinned by nothing here; a breaking release shows up at step 3.
