# Prose: hand off, do not check here

This file routes; the humanizer chain owns the rules.

## What goes to the chain

Anything published under the owner's name or read by the public: README, CHANGELOG
prose, ADR and spec abstracts, site copy, front-end microcopy, X posts, recording
intros. If in doubt, it goes.

## The chain, in this order

1. `emiliyan-humanizer` (global, `~/.claude/skills/emiliyan-humanizer/`): voice first,
   then it runs the generic `humanizer` with the exceptions table. Run the other way
   round, the humanizer strips the devices that are his.
2. It ends with `Done:` and `Kept as his:`. Both lines go into your report unchanged;
   the owner reads them.

The tell list, the rhythm numbers, the public-copy register and the exceptions table
live in the chain, not here.

Never run a script that rewrites prose. A regex cannot tell a tell from a voice; the
measures in `measure.md` count, they do not edit.

## The two checks for internal prose

Implementer reports, handoffs, vault notes and `factory`-branch commit messages skip
the chain (a commit message bound for `main` is public: chain it at the release
cherry-pick, the sink). They get two lines:

- Lead with the point. No stage directions ("In this section I will", "Let me break
  this down"), no chatbot residue ("I hope this helps").
- Say what you did in the glossary's words. "leverage" and "adapter" are binding terms
  in design prose; do not "fix" them.
