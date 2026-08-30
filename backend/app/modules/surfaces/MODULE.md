# surfaces

- Interface: one prefix contributor, `WebSurfaceContributor`, owning slot L4. It is registered with `context.register_prefix` at import, so importing `app.modules` is what puts the surface contract in front of the model, exactly as it is what declares an operation.
- L4 is the surface contract: what a reply is on this surface, how intake arrives, and when the agent stops. It was a kernel constant through wave 8 and moved here when the owner's D2 fell due (2026-08-30). A second surface is a second contributor in this module, never a kernel edit.
- The text is Fable-authored prompt wording (AGENTS.md, Model routing) and is installed verbatim; changing it is that route's change, not an implementer's.
- The layer's version is a content digest of the body, like every other layer's, so a reworded contract moves `prefix_key` and no cached prefix survives it (ADR-0014).
- D6 stays the kernel's: the L4 contract already opens by naming the surface, so a separate identity line in the envelope would be a second copy of the same fact, and the intake slice stays where it is (`runs/work.py`, `_intake`) — the port hands a `Turn` and the worker is the one drain of the mailbox. Settled 2026-08-31; a second surface needing a per-envelope identity reopens it.
- Not built either: any store of its own. A surface has no table in Phase 1.
