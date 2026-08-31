# context

- Interface: `assemble(session, run, step_no, *, call, registry) -> AssembledTurn` — `call` carries the turn's budget and its intake, `registry` is what L5 renders from — plus `tokens(body)` and `register_prefix(contributor)`, and the two contributor protocols in `ports/context_contributor.py`, byte-verbatim from ADR-0027. `tokens(body)` is the one tokenizer; contributors never count.
- Prefix: L0 platform constant · L1–L3 from `instructions` · L4 from the registered prefix contributor that owns it (`modules/surfaces` since wave 9, via `register_prefix`) · L5 the registry's tool schemas for the PROD operations the run's ceiling allows · L6 the skill directory. `prefix_key` = sha256 over the ordered `(slot, owner, version)` sequence + the tool-schema hash + the tier binding (ADR-0014).
- Envelope: D1 the run's bound skill body; D5 and D6 are filled by the worker's intake assembly (`runs/work.py`, since wave 8; settled to stay there, 2026-08-31); over budget drops slices by declared priority, never a prefix layer, never silently.
- Layer versions are content digests (`term:sha256[:16]`) until a versioned store exists; equal versions mean equal bytes, proven per adapter by the Hypothesis determinism test.
- Mapped: `context_manifest`, column for column with migration 0001; one row per assemble call.
- Not built: the memory contributor (the third adapter ADR-0027 names), per-contributor budgets and horizon-gating (parked with trigger), cache telemetry (the model module writes it onto the manifest).
- Tests: `tests/test_assemble.py` and `tests/test_contributors.py` against a real Postgres at head.
