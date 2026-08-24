---
name: scrub-gate
description: Grep files at the sink for provenance leaks with the vault's pre-tag pattern, then print the by-eye read list. Fable or the owner fire it before anything goes public.
disable-model-invocation: true
---

# scrub-gate

The rule is AGENTS.md, Provenance boundary. The pattern list is vault data (`$V` as defined in AGENTS.md, `$V/30-research/2026-08-23-release-1-compliance.md`, the pre-tag grep gate line); the script reads it at run time, so this repo never carries the words.

## Procedure

1. Scan at the sink: run `bash .claude/skills/scrub-gate/scripts/scrub.sh [paths]` on the files that are actually passed on (the staged tree, the cherry-pick, the file handed to a web search), never on a re-rendered string. Default with no paths: the staged content. Done: exit 0, or every hit listed as `file:line`.
2. A hit blocks: the content is fixed at the source and re-scanned. A blocked body is persisted nowhere else (no scratch copy, no vault note quoting it). Done: re-run exits 0.
3. Provenance comes from the path: a file under the vault or under `.claude/` is private until scanned, whatever its text claims about itself. Done: the scan ran on the file that crosses, not on a claim.
4. Read every new public file by eye against the printed register (public-copy words are judged in context, so the script lists them instead of grepping them). Done: the reader's name and date in the release checklist.

## Limits

A grep catches the listed words only; paraphrase, pilot-business details and internal hostnames outside the pattern are the by-eye read's job. The script needs the vault next door; without it, exit 2 and nothing crosses.
