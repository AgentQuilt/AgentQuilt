# context

- Interface: `assemble(session, run, step_no) -> AssembledTurn`, and the two contributor protocols in `ports/context_contributor.py`, byte-verbatim from ADR-0027. `tokens(body)` is the one tokenizer; contributors never count.
- Prefix: L0 platform constant · L1–L3 from `instructions` · L4 a kernel constant until `surfaces` lands in wave 9 (owner decision, 2026-08-30) · L5 the registry's tool schemas filtered by effective grants · L6 the skill directory. `prefix_key` = sha256 over the ordered `(slot, owner, version)` sequence + the tool-schema hash + the tier binding (ADR-0014).
- Envelope: D1 the run's bound skill body; D5 and D6 exist as slots with no producer until the worker and intake arrive; over budget drops slices by declared priority, never a prefix layer, never silently.
- Layer versions are content digests (`term:sha256[:16]`) until a versioned store exists; equal versions mean equal bytes, proven per adapter by the Hypothesis determinism test.
- Mapped: `context_manifest`, column for column with migration 0001; one row per assemble call.
- Not built: the memory contributor (the third adapter ADR-0027 names), a surfaces adapter, per-contributor budgets and horizon-gating (parked with trigger), cache telemetry (the model module writes it onto the manifest).
- Tests: `tests/test_assemble.py` and `tests/test_contributors.py` against a real Postgres at head.
