# store

- Interface: `session(org_id, environment_id, principal_id)`, an async context manager, `engine()`, `tenants()` (every (org, environment, principal) triple a background role acts as) and `seed()`; `Scope` is that triple, declared once here.
- Scoped: every session opens `SET LOCAL ROLE agentquilt_app` and sets `app.org_id`, `app.environment_id` and `app.principal_id` for the transaction, so two-key RLS answers every read and the GUC default fills every insert's plane.
- Mapped: `org`, `user`, `principal`, `agent_definition`, `user_token`, `environment` and `skill_binding`, column for column with migrations 0001-0004; `seed()` writes the two demo orgs, each with its dev and prod planes, through the scoped path on purpose.
- Not built: relationships, repositories, an unscoped session, and any read of the ledger tables.
- Tests: `tests/test_tenancy.py` against a real Postgres at head.
