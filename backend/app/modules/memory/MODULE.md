# memory

- What this module owns in Phase 1 is a fact, not a table: the text behind the prefix's instruction layers. The org's own instructions (L1), the agent's soul (L2) and the person's profile (L3) are rows on `core.agent_definition` and `core.user`, and `memory` is the module that owns them there.
- Interface: none yet. There is no `mod_memory` schema, no table and no declared operation. The `instructions` contributor in `kernel/context/contributors.py` renders the three layers from those rows and names this module as the owner of what it reads; when a curated store lands, the rows move behind it and the slots, their order and their versions do not change (ADR-0027 names `memory` as the third adapter, on the condition that it needs no contract change).
- Why the module exists with no code: the ownership is what stops a second module writing org text or a profile somewhere else, and ADR-0010's two-stage memory writes have to land against a named owner. Deletion test: delete this page and the next module to want a profile writes its own table.
- Not built: `mod_memory`, the two-stage write (ADR-0010), curation, retrieval, and the `memory` context contributor itself.
