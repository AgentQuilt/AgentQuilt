---
name: catchup
description: Re-read the standing context (AGENTS.md, decision-log head, open questions, latest session log, branch diff) and report; changes nothing. Fable fires it at session start or after a compaction.
disable-model-invocation: true
---

# catchup

`$V` as defined in AGENTS.md. Read, in order, and change nothing:

1. `AGENTS.md`, end to end.
2. `head -40 $V/90-meta/decision-log.md` and `$V/90-meta/open-questions.md`.
3. The newest file in `$V/90-meta/session-log/`; its "Not done / carried" list is the backlog.
4. `git branch --show-current` and `git diff --stat $(git merge-base factory HEAD)..HEAD`.

## Output

Five lines: branch and diff size; the three newest decisions; open questions touching the current work; the carried backlog; what the next step is by the session log. Every line cites its path.

## Limits

Reads only what is listed; a decision recorded elsewhere (an executive note, an ADR) is not seen here.
