"""Close the environment rail: the plane is required, defaulted and enforced.

Revision ID: 0004
Revises: 0003
Create Date: 2026-08-31

The contract half of 0003's expand (ADR-0028 D2). 0003 could not do any of this,
because no session set `app.environment_id` yet; this migration lands in the wave
whose sessions do, so every piece of it is safe on the same day:

* the column is NOT NULL, after one more backfill for rows written during expand;
* it DEFAULTs from the session GUC, so a writer carries its plane with no
  plumbing and an insert from a session without the GUC fails on the cast —
  writes fail closed exactly as reads do;
* the org policies on the eleven env-scoped tables and on `skill_binding` become
  two-key. `core.environment` stays single-key: it is the lookup table a session
  reads to know which plane it is on;
* the original single-column foreign keys go. They were kept in 0003 because a
  composite key is MATCH SIMPLE and so unchecked while `environment_id` is NULL;
  now that it is NOT NULL the `_scope` keys check everything the originals did,
  and the pair as well;
* `idempotency_key`'s primary key grows the plane, so a DEV replay cannot eat a
  PROD reservation. It waited for this migration because a primary key forces
  NOT NULL.

It also ties a user token to its user's org (owner, 2026-08-31): nothing today
forbids a token whose org differs from the user's it names.
"""

from __future__ import annotations

from alembic import op

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | None = None
depends_on: str | None = None

APP_ROLE = "agentquilt_app"
LEDGER_ROLE = "agentquilt_ledger_writer"

# The plane a writer's row lands on, read off the session. No `missing_ok`: an
# insert from a session that never set the GUC is meant to raise.
PLANE_DEFAULT = "current_setting('app.environment_id')::uuid"

# 0003's eleven, in its order.
ENV_SCOPED = (
    ("core", "run"),
    ("core", "step_queue"),
    ("core", "mailbox_message"),
    ("core", "checkpoint"),
    ("core", "context_manifest"),
    ("core", "usage_record"),
    ("core", "approval"),
    ("core", "event"),
    ("core", "action"),
    ("core", "stream_head"),
    ("core", "idempotency_key"),
)
# Every table whose policy names the plane. `skill_binding` was born with the
# column NOT NULL in 0003, so only its policy is left to swap.
TWO_KEY = (*ENV_SCOPED, ("mod_skills", "skill_binding"))

# (schema, table, name, referent, local columns, remote columns, deferred) — the
# single-column keys the `_scope` keys shadow, listed so downgrade rebuilds them.
SHADOWED_FK = (
    ("core", "step_queue", "fk_step_queue_run", "run", ["run_id"], ["id"], False),
    (
        "core", "mailbox_message", "fk_mailbox_message_run", "run",
        ["run_id"], ["id"], False,
    ),
    ("core", "checkpoint", "fk_checkpoint_run", "run", ["run_id"], ["id"], False),
    (
        "core", "context_manifest", "fk_context_manifest_run", "run",
        ["run_id"], ["id"], False,
    ),
    (
        "core", "usage_record", "fk_usage_record_run", "run",
        ["run_id"], ["id"], False,
    ),
    ("core", "run", "fk_run_parent", "run", ["parent_id"], ["id"], False),
    ("core", "action", "fk_action_event", "event", ["event_id"], ["id"], False),
    # The 0002 pair; the `_scope` key that replaces it keeps deferrable/initially.
    ("core", "event", "fk_event_action", "action", ["action_id"], ["id"], True),
    (
        "core", "stream_head", "fk_stream_head_event", "event",
        ["last_event_id"], ["id"], False,
    ),
    (
        "core", "idempotency_key", "fk_idempotency_key_action", "action",
        ["action_id"], ["id"], False,
    ),
    # A token's org is its user's org, or the two disagree and nothing notices.
    ("core", "user_token", "fk_user_token_user", "user", ["user_id"], ["id"], False),
)

# Postgres' own name for the unnamed primary key 0001 declared.
IDEMPOTENCY_PK = "idempotency_key_pkey"
IDEMPOTENCY_KEY_COLUMNS = ("org_id", "operation_name", "idempotency_key")


def _policy(schema: str, table: str, predicate: str) -> None:
    """Replace one table's row-level policy; the grants 0001 made stand."""
    op.execute(f'DROP POLICY rls_{table} ON {schema}."{table}"')
    op.execute(
        f'CREATE POLICY rls_{table} ON {schema}."{table}" FOR ALL '
        f"TO {APP_ROLE}, {LEDGER_ROLE} "
        f"USING ({predicate}) WITH CHECK ({predicate})"
    )


ORG_KEY = "org_id = current_setting('app.org_id', true)::uuid"
PLANE_KEY = "environment_id = current_setting('app.environment_id', true)::uuid"


def upgrade() -> None:
    # Whatever was written while the column was nullable belongs to the plane
    # 0003 put everything else on.
    for schema, table in ENV_SCOPED:
        op.execute(
            f"UPDATE {schema}.{table} AS t SET environment_id = e.id"
            " FROM core.environment e"
            " WHERE e.org_id = t.org_id AND e.kind = 'prod'"
            " AND t.environment_id IS NULL"
        )
        op.execute(
            f"ALTER TABLE {schema}.{table}"
            f" ALTER COLUMN environment_id SET DEFAULT {PLANE_DEFAULT},"
            " ALTER COLUMN environment_id SET NOT NULL"
        )

    for schema, table, name, *_rest in SHADOWED_FK:
        op.drop_constraint(name, table, type_="foreignkey", schema=schema)
    # What the token's new pair points at.
    op.create_unique_constraint(
        "uq_user_org_id", "user", ["org_id", "id"], schema="core"
    )
    op.create_foreign_key(
        "fk_user_token_user_org",
        "user_token",
        "user",
        ["org_id", "user_id"],
        ["org_id", "id"],
        source_schema="core",
        referent_schema="core",
    )

    op.drop_constraint(
        IDEMPOTENCY_PK, "idempotency_key", type_="primary", schema="core"
    )
    op.create_primary_key(
        IDEMPOTENCY_PK,
        "idempotency_key",
        ["environment_id", *IDEMPOTENCY_KEY_COLUMNS],
        schema="core",
    )

    for schema, table in TWO_KEY:
        _policy(schema, table, f"{ORG_KEY} AND {PLANE_KEY}")


def downgrade() -> None:
    for schema, table in TWO_KEY:
        _policy(schema, table, ORG_KEY)

    op.drop_constraint(
        IDEMPOTENCY_PK, "idempotency_key", type_="primary", schema="core"
    )
    # Planes made the same (org, operation, key) triple legal once per plane; the
    # environment-blind key cannot hold both. A downgrade collapses planes, so it
    # keeps the prod row -- the same philosophy as 0003's backfill, where the
    # pre-plane world was prod -- and drops the dev twin.
    op.execute(
        "DELETE FROM core.idempotency_key ik"
        " USING core.environment e"
        " WHERE ik.org_id = e.org_id AND ik.environment_id = e.id"
        "   AND e.kind <> 'prod'"
        "   AND EXISTS (SELECT 1 FROM core.idempotency_key k2"
        "     WHERE k2.org_id = ik.org_id"
        "       AND k2.operation_name = ik.operation_name"
        "       AND k2.idempotency_key = ik.idempotency_key"
        "       AND k2.ctid <> ik.ctid)"
    )
    op.create_primary_key(
        IDEMPOTENCY_PK,
        "idempotency_key",
        list(IDEMPOTENCY_KEY_COLUMNS),
        schema="core",
    )

    op.drop_constraint(
        "fk_user_token_user_org", "user_token", type_="foreignkey", schema="core"
    )
    op.drop_constraint("uq_user_org_id", "user", type_="unique", schema="core")
    for schema, table, name, parent, local, remote, deferred in SHADOWED_FK:
        op.create_foreign_key(
            name,
            table,
            parent,
            local,
            remote,
            source_schema=schema,
            referent_schema=schema,
            deferrable=True if deferred else None,
            initially="DEFERRED" if deferred else None,
        )

    for schema, table in ENV_SCOPED:
        op.execute(
            f"ALTER TABLE {schema}.{table}"
            " ALTER COLUMN environment_id DROP DEFAULT,"
            " ALTER COLUMN environment_id DROP NOT NULL"
        )
