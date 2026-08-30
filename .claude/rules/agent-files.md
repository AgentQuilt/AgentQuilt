---
paths: [".claude/**/*.md", "AGENTS.md", "REVIEW.md"]
---

# Writing factory files (agents, skills, rules, AGENTS.md, REVIEW.md)

- Description: at most 30 words, third person, what it does plus when to reach for it. One trigger per branch (synonyms are one branch written twice); add an explicit non-trigger where a wrong invocation is likely.
- Body caps: agents 60 lines, skills 110; detail goes in `references/`, one level deep.
- Every procedural step ends on a done-condition the reader can check.
- Phrase positively: say what to do, and pair any prohibition with the target behaviour.
- Apply the deletion test to instructions: delete the line, and if behaviour would not change, it stays deleted. An instruction the model already follows by default only costs context.
- Describe the present; a doc that restates a script or config is a stale cache.
- Reference a rule by name and file; one rule has one home, and the other files point at it.
- Use the glossary's word as the leading word; never coin.
- Write vault paths as `$V/...`; `$V` is defined once, in AGENTS.md, and never restated.
- Give a project skill a name no user-level skill (`~/.claude/skills/`) uses; the project copy would lose.
- `disable-model-invocation: true` blocks every model invocation, Fable's included, so only a skill the owner alone fires carries it; a skill Fable fires stays model-invocable, its trigger stated in the description (owner, 2026-08-27).
- Sentence case for emphasis; plain imperatives.
