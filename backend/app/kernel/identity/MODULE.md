# identity

- Interface: `resolve(session, token) -> Principal | None`, `effective_grants(session, principal_id) -> Mapping[operation_name, level]` and `args_hash(operation_version_id, args, scope) -> str`. Plain functions over the two tables: no port, no policy engine, no second evaluator (ADR-0026), and dispatch is the only caller.
- Grants: `effective_grants` returns the step's set, which ADR-0015:18 defines as root ceiling ∩ narrowing state ∩ the acting principal's grants. Phase 1 has an always-empty narrowing state and an acting principal who is the originator, so the principal's own `core.grant` rows are the whole intersection.
- `args_hash` is SHA-256 over `"agentquilt.approval.v1"`, the operation version id, the RFC 8785 canonical form of the args (`rfc8785`) and the target scope, joined by a `\x00` separator so one field's value cannot be read as another's. It is compared only against itself.
- Mapped: `grant` and `approval`, column for column with migration 0001; the drift test in `store/tests` reads them with the rest of the metadata.
- Not built: roles (`core.role` is unmapped), grant scopes (`scope_form` and `scope_ref` are stored and never read), narrowing state, and any read of a token outside `resolve`.
