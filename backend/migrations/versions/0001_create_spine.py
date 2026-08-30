"""Create the spine: schemas, roles, tenant and ledger tables, RLS.

Revision ID: 0001
Revises:
Create Date: 2026-08-30
"""

from __future__ import annotations

from typing import Any

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | None = None
depends_on: str | None = None

UUID = postgresql.UUID(as_uuid=True)
JSONB = postgresql.JSONB
NOW = sa.text("now()")

APP_ROLE = "agentquilt_app"
LEDGER_ROLE = "agentquilt_ledger_writer"

# Creation order: every foreign key points at a table above it, so the reverse
# is a safe drop order.
CREATE_ORDER = (
    "org",
    "user",
    "principal",
    "agent_definition",
    "user_token",
    "role",
    "grant",
    "event",
    "stream_head",
    "operation_version",
    "action",
    "idempotency_key",
    "approval",
)
# Deployment-global: no org_id, so no row-level security.
GLOBAL_TABLES = ("operation_version",)
# RLS keys on org_id, or on id for org itself.
TENANT_TABLES = tuple(t for t in CREATE_ORDER if t not in GLOBAL_TABLES)
# No role may UPDATE or DELETE these: the ledger is append-only (ADR-0002).
APPEND_ONLY = ("event", "action")
LEDGER_WRITABLE = ("stream_head", "idempotency_key", "approval")


def _org_id(table: str) -> sa.Column[Any]:
    """The tenant key, with the foreign key naming-conventions.md asks for."""
    return sa.Column(
        "org_id",
        UUID,
        sa.ForeignKey("core.org.id", name=f"fk_{table}_org"),
        nullable=False,
    )


def _created_at() -> sa.Column[Any]:
    return sa.Column(
        "created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=NOW
    )


def upgrade() -> None:
    op.execute("CREATE SCHEMA core")
    op.execute("CREATE SCHEMA mod_skills")
    # CREATE ROLE has no IF NOT EXISTS, and roles are cluster-wide: a second
    # database on the same cluster may already have created them.
    for role in (APP_ROLE, LEDGER_ROLE):
        op.execute(
            f"DO $$ BEGIN IF NOT EXISTS ("
            f"SELECT FROM pg_roles WHERE rolname = '{role}'"
            f") THEN CREATE ROLE {role} NOLOGIN; END IF; END $$"
        )
    op.execute(
        f"GRANT USAGE ON SCHEMA core, mod_skills TO {APP_ROLE}, {LEDGER_ROLE}"
    )

    op.create_table(
        "org",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("name", sa.Text, nullable=False),
        _created_at(),
        schema="core",
    )
    op.create_table(
        "user",
        sa.Column("id", UUID, primary_key=True),
        _org_id("user"),
        sa.Column("display_name", sa.Text, nullable=False),
        _created_at(),
        schema="core",
    )
    op.create_table(
        "principal",
        sa.Column("id", UUID, primary_key=True),
        _org_id("principal"),
        sa.Column("class", sa.Text, nullable=False),
        sa.Column(
            "user_id",
            UUID,
            sa.ForeignKey("core.user.id", name="fk_principal_user"),
            nullable=True,
        ),
        _created_at(),
        sa.CheckConstraint(
            "\"class\" IN ('user', 'agent', 'run', 'system', 'external')",
            name="ck_principal_class",
        ),
        schema="core",
    )
    op.create_table(
        "agent_definition",
        sa.Column("id", UUID, primary_key=True),
        _org_id("agent_definition"),
        sa.Column("name", sa.Text, nullable=False),
        sa.Column("version", sa.Integer, nullable=False),
        sa.Column("soul_text", sa.Text, nullable=False),
        sa.Column("tier", sa.Text, nullable=False),
        sa.Column("budget_cap_tokens", sa.Integer, nullable=False),
        sa.Column("memory_scope", sa.Text, nullable=False),
        _created_at(),
        sa.UniqueConstraint(
            "org_id", "name", "version", name="uq_agent_definition_org_name_version"
        ),
        schema="core",
    )
    op.create_table(
        "user_token",
        sa.Column("id", UUID, primary_key=True),
        sa.Column(
            "user_id",
            UUID,
            sa.ForeignKey("core.user.id", name="fk_user_token_user"),
            nullable=False,
        ),
        _org_id("user_token"),
        sa.Column("token_hash", sa.Text, nullable=False),
        _created_at(),
        sa.Column("revoked_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.UniqueConstraint("token_hash", name="uq_user_token_token_hash"),
        schema="core",
    )
    op.create_table(
        "role",
        sa.Column("id", UUID, primary_key=True),
        _org_id("role"),
        sa.Column("name", sa.Text, nullable=False),
        schema="core",
    )
    op.create_table(
        "grant",
        sa.Column("id", UUID, primary_key=True),
        _org_id("grant"),
        sa.Column(
            "principal_id",
            UUID,
            sa.ForeignKey("core.principal.id", name="fk_grant_principal"),
            nullable=False,
        ),
        sa.Column("operation_name", sa.Text, nullable=False),
        sa.Column("level", sa.Text, nullable=False),
        sa.Column(
            "scope_form", sa.Text, nullable=False, server_default=sa.text("'entity'")
        ),
        sa.Column("scope_ref", sa.Text, nullable=True),
        sa.CheckConstraint(
            "level IN ('may_use', 'asks_first', 'never')", name="ck_grant_level"
        ),
        sa.CheckConstraint(
            "scope_form IN ('entity', 'node_plus_descendants', 'all_of_type')",
            name="ck_grant_scope_form",
        ),
        schema="core",
    )

    op.create_table(
        "event",
        sa.Column("id", sa.BigInteger, sa.Identity(always=True), primary_key=True),
        _org_id("event"),
        sa.Column("kind", sa.Text, nullable=False),
        sa.Column("aggregate_kind", sa.Text, nullable=False),
        sa.Column("aggregate_id", UUID, nullable=False),
        sa.Column("aggregate_version", sa.Integer, nullable=False),
        sa.Column("run_id", UUID, nullable=True),
        sa.Column("step_no", sa.Integer, nullable=True),
        sa.Column("principal_id", UUID, nullable=False),
        sa.Column("operation_name", sa.Text, nullable=True),
        sa.Column("payload", JSONB, nullable=False),
        _created_at(),
        sa.CheckConstraint(
            "kind IN ('operation_commit', 'run_journal', 'read_audit', 'denial')",
            name="ck_event_kind",
        ),
        schema="core",
    )
    # Raw SQL because this is a partial index: it carries the uq_ prefix its
    # uniqueness earns, which the migration lint reserves for constraints.
    op.execute(
        "CREATE UNIQUE INDEX uq_event_org_aggregate_version ON core.event "
        "(org_id, aggregate_kind, aggregate_id, aggregate_version) "
        "WHERE kind = 'operation_commit'"
    )
    op.create_table(
        "stream_head",
        _org_id("stream_head"),
        sa.Column("aggregate_kind", sa.Text, nullable=False),
        sa.Column("aggregate_id", UUID, nullable=False),
        sa.Column("version", sa.Integer, nullable=False),
        sa.Column(
            "last_event_id",
            sa.BigInteger,
            sa.ForeignKey("core.event.id", name="fk_stream_head_event"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("org_id", "aggregate_kind", "aggregate_id"),
        schema="core",
    )
    op.create_table(
        "operation_version",
        sa.Column("id", sa.Text, primary_key=True),
        sa.Column("operation_name", sa.Text, nullable=False),
        sa.Column("stage", sa.Text, nullable=False),
        sa.Column("declaration", JSONB, nullable=False),
        _created_at(),
        sa.CheckConstraint(
            "stage IN ('DEV', 'QA', 'PROD')", name="ck_operation_version_stage"
        ),
        schema="core",
    )
    op.create_table(
        "action",
        sa.Column("id", UUID, primary_key=True),
        _org_id("action"),
        sa.Column(
            "event_id",
            sa.BigInteger,
            sa.ForeignKey("core.event.id", name="fk_action_event"),
            nullable=False,
        ),
        sa.Column(
            "operation_version_id",
            sa.Text,
            sa.ForeignKey(
                "core.operation_version.id", name="fk_action_operation_version"
            ),
            nullable=False,
        ),
        sa.Column("approval_id", UUID, nullable=True),
        sa.Column("idempotency_key", sa.Text, nullable=False),
        sa.Column("decision_trace", JSONB, nullable=False),
        sa.Column("compensator_ref", sa.Text, nullable=True),
        sa.Column("compensator_args", JSONB, nullable=True),
        sa.Column("external_attempt", JSONB, nullable=True),
        sa.Column("external_observation", JSONB, nullable=True),
        _created_at(),
        sa.UniqueConstraint("event_id", name="uq_action_event"),
        schema="core",
    )
    op.create_table(
        "idempotency_key",
        _org_id("idempotency_key"),
        sa.Column("operation_name", sa.Text, nullable=False),
        sa.Column("idempotency_key", sa.Text, nullable=False),
        sa.Column(
            "action_id",
            UUID,
            sa.ForeignKey("core.action.id", name="fk_idempotency_key_action"),
            nullable=True,
        ),
        sa.PrimaryKeyConstraint("org_id", "operation_name", "idempotency_key"),
        schema="core",
    )
    op.create_table(
        "approval",
        sa.Column("id", UUID, primary_key=True),
        _org_id("approval"),
        sa.Column(
            "granted_to",
            UUID,
            sa.ForeignKey("core.principal.id", name="fk_approval_granted_to"),
            nullable=False,
        ),
        sa.Column(
            "granted_by",
            UUID,
            sa.ForeignKey("core.principal.id", name="fk_approval_granted_by"),
            nullable=True,
        ),
        sa.Column(
            "operation_version_id",
            sa.Text,
            sa.ForeignKey(
                "core.operation_version.id", name="fk_approval_operation_version"
            ),
            nullable=False,
        ),
        sa.Column("args_hash", sa.Text, nullable=False),
        sa.Column("state", sa.Text, nullable=False),
        sa.Column("reason", sa.Text, nullable=True),
        sa.Column("run_id", UUID, nullable=False),
        sa.Column("step_no", sa.Integer, nullable=False),
        sa.Column("tool_call_id", sa.Text, nullable=False),
        sa.Column("expires_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("consumed_by_action_id", UUID, nullable=True),
        _created_at(),
        sa.CheckConstraint(
            "state IN ('requested', 'open', 'consumed', 'rejected', 'expired',"
            " 'superseded')",
            name="ck_approval_state",
        ),
        schema="core",
    )
    op.create_index(
        "ix_approval_org_state", "approval", ["org_id", "state"], schema="core"
    )

    for table in TENANT_TABLES:
        key = "id" if table == "org" else "org_id"
        predicate = f"{key} = current_setting('app.org_id', true)::uuid"
        op.execute(f'ALTER TABLE core."{table}" ENABLE ROW LEVEL SECURITY')
        op.execute(f'ALTER TABLE core."{table}" FORCE ROW LEVEL SECURITY')
        op.execute(
            f'CREATE POLICY rls_{table} ON core."{table}" FOR ALL '
            f"TO {APP_ROLE}, {LEDGER_ROLE} "
            f"USING ({predicate}) WITH CHECK ({predicate})"
        )
        if table in APPEND_ONLY:
            op.execute(f'GRANT SELECT ON core."{table}" TO {APP_ROLE}')
            op.execute(f'GRANT INSERT ON core."{table}" TO {LEDGER_ROLE}')
        else:
            op.execute(
                f'GRANT SELECT, INSERT, UPDATE, DELETE ON core."{table}" TO {APP_ROLE}'
            )
    for table in LEDGER_WRITABLE:
        op.execute(
            f'GRANT SELECT, INSERT, UPDATE ON core."{table}" TO {LEDGER_ROLE}'
        )
    op.execute(
        f"GRANT SELECT ON core.operation_version TO {APP_ROLE}, {LEDGER_ROLE}"
    )
    op.execute(f"GRANT INSERT ON core.operation_version TO {APP_ROLE}")


def downgrade() -> None:
    for table in reversed(CREATE_ORDER):
        op.drop_table(table, schema="core")
    op.execute("DROP SCHEMA mod_skills")
    op.execute("DROP SCHEMA core")
    op.execute(f"DROP ROLE IF EXISTS {LEDGER_ROLE}")
    op.execute(f"DROP ROLE IF EXISTS {APP_ROLE}")
