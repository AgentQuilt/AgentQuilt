# Prose: hand off, do not check here

This skill checks code. Prose has its own chain, and the chain owns every rule about
it. Nothing below duplicates the chain; it only routes to it.

## What goes to the chain

Anything published under the owner's name or read by the public: README, CHANGELOG
prose, ADR and spec abstracts, site copy, front-end microcopy, X posts, recording
intros. If in doubt, it goes.

## The chain, in this order

1. `emiliyan-humanizer` (global, `~/.claude/skills/emiliyan-humanizer/`): it loads the
   register, the voice profile and the worked examples, then runs the generic
   `humanizer` with the exceptions table. Voice first, then the humanizer; run the
   other way round, the humanizer strips the devices that are his.
2. It ends with `Done:` and `Kept as his:`. Both lines go into your report unchanged;
   the owner reads them.

## What stays in the chain and not here

- The tell list (the humanizer's pattern families).
- The rhythm numbers (words per sentence, share of short sentences, paragraph length).
- The public-copy register: forbidden words, the provenance scrub, "your own database"
  not Postgres, no em dashes.
- The exceptions table: rule of three, anaphora, fragments, Title Case in essays, and
  the other devices a generic checker flags that are his voice.

Never run a script that rewrites prose. A regex cannot tell a tell from a voice; the
measures in `measure.md` count, they do not edit.

## The two checks for internal prose

Implementer reports, handoffs, commit messages and vault notes skip the chain. They
get two lines:

- Lead with the point. No stage directions ("In this section I will", "Let me break
  this down"), no chatbot residue ("I hope this helps").
- Say what you did in the glossary's words. "leverage" and "adapter" are binding terms
  in design prose; do not "fix" them.
