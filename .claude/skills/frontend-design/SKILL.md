---
name: frontend-design
description: Procedure for a surface task under `frontend/`: tokens first, one exemplar, copy rules, accessibility floor, hand-off to browser-qa. The implementer fires it; not for backend or prose tasks.
---

# frontend-design

Run on any task that adds or changes something under `frontend/`. Rules it applies live elsewhere: reuse-before-create and map-outdated in `.claude/rules/architecture.md`, React and budgets in `.claude/rules/typescript.md`, the diff self-check in `anti-slop`. This skill adds what those do not say about a surface.

## Procedure

1. Name the surface, the principal who uses it and the one job or decision it serves, in glossary words, from the brief and the spec. Done: one sentence at the top of the report.
2. Read `frontend/src/design-system/tokens/` and `COMPONENTS.md` before writing anything. Done: the catalog entries this task composes are listed; a raw colour, size or font in module code is a finding against yourself.
3. reuse-before-create per visual object: compose an existing primitive or pattern, or extend it in the design system with a catalog entry in the same change. Done: each new part has its reuse line; no primitive is redefined in a module.
4. Build one exemplar first (the smallest instance the task needs), then the rest from it. Done: the exemplar's path is in the report.
5. Copy: name things by what the person controls, never by how the system is built; a control says what happens ("Save changes", not "Submit") and keeps that verb through the flow and its result; errors say what happened and what to do next, without apology; an empty state says what to do first. Structural devices (numbers, dividers, labels) encode something true about the content, so a numbered marker appears only where order carries meaning. Done: every visible string checked against these lines.
6. Floor before hand-off: works at phone width where the spec requires it, visible keyboard focus on every control, `prefers-reduced-motion` respected, text contrast holds on the tokens used. Done: the four checked, with what was observed.
7. Run `anti-slop` on the diff, then report; the orchestrator sends the surface to `browser-qa` for evidence. Done: the report names the acceptance items browser-qa should walk.

Stop and report instead of guessing when a token, primitive or copy the task needs does not exist in the design language, or when the brief leaves the surface's job open.

## Design language

Placeholder until the owner's design language is written; then this section is one line pointing at it (`$V/docs/architecture/design-language.md`, proposed path, open question). Until then the settled parts are the brand-colour decision in `$V/90-meta/decision-log.md` (2026-08-18: field, thread, patches, one accent, no gradients, stitch motif) and the design-system layout in `$V/docs/architecture/system-structure.md`; type, spacing, motion and iconography are open, and a task that needs them stops (procedure, last line).

## Output contract

Surface sentence (step 1) · catalog entries composed and any added · exemplar path · copy check · floor check with observations · acceptance items for browser-qa · `Done:` / `Left out:`.

## Limits

Dormant until `frontend/` exists. It checks procedure and floor, not taste; whether the result matches the design language is the owner's read at the gate until that language is a document. It verifies nothing in a browser.
