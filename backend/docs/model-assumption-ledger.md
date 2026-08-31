# Model-assumption ledger

Structure this codebase carries because of what today's models cannot do. Each
entry names the weakness it works around, the model generation it was observed on,
the code that carries it, and how to detect the weakness is gone — the deletion
trigger. An entry with no trigger is not an entry; a workaround nobody can retire
becomes architecture by default.

Entries are added by the change that introduces the workaround, and retired by the
change that removes it. ADR numbers are the source; they are in the vault.

## 1. The prefix/envelope split

**Assumption.** A model call is cheaper and faster when the bytes in front of it do
not move, so the prompt is built as one byte-stable prefix (the tool block plus
L0–L6) followed by a dynamic envelope (D1, D3–D6), and the prefix's identity is a
key (`prefix_key`) that changes whenever any layer's content changes.

**Weakness worked around.** Providers cache a prompt by its literal leading bytes,
in the order tools → instructions → messages, and bill cached input at a fraction
of fresh input. One byte changed anywhere in that lead re-bills everything after
it, so a prompt assembled per turn in natural order costs full price on every turn
of a long run. Models also have no memory between calls: the whole standing context
is resent each time, which is why the lead is large enough for this to matter.

**Observed on.** The 2026-08 provider generation, read against provider
documentation on 2026-08-22 (ADR-0006, ADR-0014): up to four cache positions per
request with a bounded lookback, one provider requiring an explicit cache key, and
both rendering the reasoning-effort setting into the prompt, so an effort-only
re-bind invalidates every cached prefix on that tier.

**Carried by.** `kernel/context/service.py` (the slot order, `prefix_key`, the
per-turn manifest), `kernel/ports/context_contributor.py` (the two contracts that
keep a contributor out of the ordering), `kernel/model/service.py` (the mandatory
cache position recorded on the manifest), and the layer ownership stated in
`kernel/context/MODULE.md`.

**Gone when.** A generation prices cached and fresh input the same, or caches by
content rather than by leading bytes, so that reordering the prompt costs nothing.
Detect it from the deployment's own rows, not from a vendor's claim:
`core.usage_record.cached_tokens` stops correlating with cost per turn, or
`core.context_manifest.telemetry` shows no hit-rate difference between runs whose
`prefix_key` was stable and runs that minted a new one every turn.

**Retire then.** The split collapses: one prompt assembled per turn in whatever
order reads best, no `prefix_key`, no cache positions. Keep the manifest — it
records what the model was told and is how an agent's belief is debugged, which no
model generation removes the need for.

## 2. The index-first skill directory

**Assumption.** A run's tool set is fixed for the life of its prefix. L6 carries the
skill *directory* (names only) and the envelope carries the body of the one version
the run is bound to (D1); an inline skill declares no operations, and a skill that
needs its own tools runs as a delegated sub-run with its own prefix.

**Weakness worked around.** Two at once. The tool block is the first thing the
provider caches, so tools that arrive when a skill activates rewrite the cached
prefix of every turn after it — this is why the earlier design (D2, full schemas
merged into the envelope on activation) could not hold. And a model's accuracy at
picking a tool falls as the tool count rises, so disclosing every skill's schemas
to every run costs correctness as well as bytes.

**Observed on.** The 2026-08 provider generation (ADR-0013, gap review 2026-08-22):
the `tools → system → messages` cache order, and provider guidance on how many
tools a request should carry. ADR-0013 retired the earlier form of this entry, an
operation *index* in L5 with schemas on activation, on 2026-08-23; the cost that
form was paying for is now paid by delegation and small per-surface tool sets.

**Carried by.** `modules/skills/service.py` (the `inline` validation and
`directory`), the `SkillsContributor` in `kernel/context/contributors.py` (L6 names,
D1 body), and L5 as the registry's grant-filtered schemas in
`kernel/context/service.py`.

**Gone when.** A generation picks correctly from the whole catalogue and caches
tool definitions independently of prompt order. Detect it: the manifest shows a
surface's tool schemas are no longer the dominant prefix cost, and a measured
selection test over the full directory matches the small-set baseline. Either
condition failing the other way — schemas becoming the dominant cost, or a core set
passing provider tool-count guidance — reopens the entry rather than retiring it.

**Retire then.** L6 carries schemas, inline skills may declare operations, and
delegation becomes a choice about isolation rather than a way to keep a prefix
still.
