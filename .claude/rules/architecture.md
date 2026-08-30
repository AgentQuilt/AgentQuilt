---
paths: ["backend/**", "docs/architecture/**"]
---

# Architecture rules (canonical wording; other files reference these kinds by name)

Source: `$V/docs/architecture/design-rules.md` and `glossary.md`. Design prose follows the vocabulary rule in AGENTS.md (Vocabulary and design rules); "module" is used in one declared sense (kernel module, buildable module, or the design sense). A new domain name gets a glossary entry in the same change.

## Checks (REVIEW.md lists them as P1 kinds; the architect states a verdict per check)

- deletion-test: state the verdict for every new module. Delete it in your head: complexity vanishes, it was a pass-through, delete it; complexity reappears across N callers, it earned its keep.
- one-adapter-seam: one adapter is a hypothetical seam, two adapters are a real one. No port without two justified adapters (typically production and test); a pure function or an in-process dependency gets no port.
- tests-past-interface: the interface is the test surface. Tests assert observable outcomes through the interface and survive internal refactors; when a deepened module's interface tests exist, delete the old shallow tests. Needing to test past the interface means the module is the wrong shape.
- design-it-twice: every major seam gets two or three genuinely different interface alternatives (minimal-surface, flexible, common-caller-optimised) before one is chosen; options differing only in naming are one option.
- judgment-as-code: judgment in skills, execution in code. Code executes a decision already made; a heuristic decision tree in code belongs in a skill. Guarantees run the other way: authorization, tenant isolation, approval binding, idempotency and audit recording live in deterministic code, never in a skill. Those five guarantees are the whole of this rule's reach; configurability of anything else (prompts, tools, tiers, channels, agent permissions) is the product's thesis, not a risk to it.
- vocabulary: the word rule in AGENTS.md (Vocabulary and design rules), plus every kernel concept, seam, registry field or ledger event kind carries an ADR number.
- map-outdated: the repo carries its own map (per-tree `INDEX.md`, per-module `MODULE.md`, catalogs); updating it is part of the change that alters what it describes, and a merged change that outdates the map is incomplete.
- reuse-before-create: creating a new function, class, module, helper or tool is the exception that argues its case. Search the catalog first; either compose or extend the closest existing part, or name it and why it does not fit, in the change description where the review gate can see it.
- tautological-test: a test that restates the implementation proves nothing; assert the behaviour the caller depends on.

## Dependency categories (how a seam is tested)

In-process (pure computation): merge and test directly, no adapter. Local-substitutable (Postgres to PGLite, filesystem to in-memory): test with the stand-in, the seam stays internal. Remote but owned: port at the seam, HTTP or queue adapter in production, in-memory adapter in tests. True external (model providers, payment-class services): injected port, mock adapter in tests. The model layer is true-external behind our own port.

## Standing rules

- Untouched core, agent-buildable periphery: a module is right when a business user with an agent can build on it without touching the core.
- Every run is an addressable module: streamable output, a steering mailbox, audit events; no fire-and-forget agent work.
- A harness workaround for a current-model weakness is a dated assumption: it gets a model-assumption-ledger entry (which weakness, which model generation, how to detect it is gone) and is revisited on every model upgrade.

## ADR discipline

Write an ADR only when the choice is hard to reverse, surprising, and a real trade-off; otherwise no ADR. ADRs live in `$V/docs/architecture/adr/`, use the seven headings, stay under sixty lines and name what was rejected as over-engineering. Every deferral names its trigger; amendments to settled text happen in the same change, never silently.
