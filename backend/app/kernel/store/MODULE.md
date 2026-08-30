# store

- Interface: `session(org_id, principal_id)`, an async context manager, and `engine()`.
- Scoped: every session opens `SET LOCAL ROLE agentquilt_app` and sets `app.org_id` and `app.principal_id` for the transaction, so RLS answers every read and write.
- Mapped: `org`, `user`, `principal`, `agent_definition`, `user_token`, column for column with migration 0001; `seed()` writes the two demo orgs through the scoped path on purpose.
- Not built: relationships, repositories, an unscoped session, and any read of the ledger tables.
- Tests: `tests/test_tenancy.py` against a real Postgres at head.
