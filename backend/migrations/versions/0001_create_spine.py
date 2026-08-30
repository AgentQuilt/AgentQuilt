"""Create the spine: schemas, roles, every table of the first migration, RLS.

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
    ("core", "org"),
    ("core", "user"),
    ("core", "principal"),
    ("core", "agent_definition"),
    ("core", "user_token"),
    ("core", "role"),
    ("core", "grant"),
    ("core", "event"),
    ("core", "stream_head"),
    ("core", "operation_version"),
    ("core", "action"),
    ("core", "idempotency_key"),
    ("core", "approval"),
    ("core", "tier"),
    ("core", "tier_binding"),
    ("mod_skills", "skill"),
    ("mod_skills", "skill_version"),
    ("core", "run"),
    ("core", "step_queue"),
    ("core", "mailbox_message"),
    ("core", "checkpoint"),
    ("core", "context_manifest"),
    ("core", "usage_record"),
)
# Deployment-global: no org_id, so no row-level security.
GLOBAL_TABLES = (
    ("core", "operation_version"),
    ("core", "tier"),
    ("core", "tier_binding"),
)
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


def _run_id(table: str) -> sa.Column[Any]:
    return sa.Column(
        "run_id",
        UUID,
        sa.ForeignKey("core.run.id", name=f"fk_{table}_run"),
        nullable=False,
    )


def _tier(table: str) -> sa.Column[Any]:
    return sa.Column(
        "tier",
        sa.Text,
        sa.ForeignKey("core.tier.name", name=f"fk_{table}_tier"),
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

    op.create_table(
        "tier",
        sa.Column("name", sa.Text, primary_key=True),
        sa.CheckConstraint(
            "name IN ('orchestrator', 'executor', 'simple', 'image')",
            name="ck_tier_name",
        ),
        schema="core",
    )
    # The four tiers are the vocabulary ADR-0009 fixes, not configuration.
    op.execute(
        "INSERT INTO core.tier (name) VALUES"
        " ('orchestrator'), ('executor'), ('simple'), ('image')"
    )
    op.create_table(
        "tier_binding",
        sa.Column("id", UUID, primary_key=True),
        _tier("tier_binding"),
        sa.Column("provider", sa.Text, nullable=False),
        sa.Column("model", sa.Text, nullable=False),
        # Not every provider takes an effort setting.
        sa.Column("effort", sa.Text, nullable=True),
        sa.Column("version", sa.Integer, nullable=False),
        _created_at(),
        schema="core",
    )
    op.create_table(
        "skill",
        sa.Column("id", UUID, primary_key=True),
        _org_id("skill"),
        sa.Column("name", sa.Text, nullable=False),
        schema="mod_skills",
    )
    op.create_table(
        "skill_version",
        sa.Column("id", sa.Text, primary_key=True),
        _org_id("skill_version"),
        sa.Column(
            "skill_id",
            UUID,
            sa.ForeignKey("mod_skills.skill.id", name="fk_skill_version_skill"),
            nullable=False,
        ),
        _tier("skill_version"),
        sa.Column("execution_mode", sa.Text, nullable=False),
        sa.Column("operations", JSONB, nullable=False),
        sa.Column("stage", sa.Text, nullable=False),
        sa.Column("body", sa.Text, nullable=False),
        _created_at(),
        sa.CheckConstraint(
            "execution_mode IN ('inline', 'delegated')",
            name="ck_skill_version_execution_mode",
        ),
        schema="mod_skills",
    )

    op.create_table(
        "run",
        sa.Column("id", UUID, primary_key=True),
        sa.Column(
            "parent_id",
            UUID,
            sa.ForeignKey("core.run.id", name="fk_run_parent"),
            nullable=True,
        ),
        _org_id("run"),
        sa.Column(
            "agent_definition_id",
            UUID,
            sa.ForeignKey(
                "core.agent_definition.id", name="fk_run_agent_definition"
            ),
            nullable=False,
        ),
        sa.Column(
            "skill_version_id",
            sa.Text,
            sa.ForeignKey(
                "mod_skills.skill_version.id", name="fk_run_skill_version"
            ),
            nullable=True,
        ),
        sa.Column("stage", sa.Text, nullable=False),
        sa.Column("state", sa.Text, nullable=False),
        sa.Column("failure_reason", sa.Text, nullable=True),
        sa.Column("budget_cap_tokens", sa.Integer, nullable=False),
        sa.Column("prefix_key", sa.Text, nullable=False),
        sa.Column("capability_ceiling", JSONB, nullable=False),
        # Root runs only: a child narrows against its parent's state.
        sa.Column("narrowing_state", JSONB, nullable=True),
        sa.Column("prefix_profile", sa.Text, nullable=False),
        sa.Column(
            "acting_external_principal_id",
            UUID,
            sa.ForeignKey("core.principal.id", name="fk_run_acting_external"),
            nullable=True,
        ),
        sa.Column("pinned_worker_id", sa.Text, nullable=True),
        sa.Column("worker_heartbeat_at", sa.TIMESTAMP(timezone=True), nullable=True),
        _created_at(),
        sa.Column(
            "updated_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=NOW,
        ),
        sa.CheckConstraint(
            "state IN ('queued', 'running', 'waiting_approval', 'succeeded',"
            " 'failed', 'cancelled')",
            name="ck_run_state",
        ),
        sa.CheckConstraint(
            "prefix_profile IN ('personal', 'space', 'none')",
            name="ck_run_prefix_profile",
        ),
        schema="core",
    )
    op.create_table(
        "step_queue",
        _org_id("step_queue"),
        _run_id("step_queue"),
        sa.Column("step_no", sa.Integer, nullable=False),
        sa.Column("queue_tag", sa.Text, nullable=False),
        sa.Column("lease_until", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("claimed_by", sa.Text, nullable=True),
        sa.PrimaryKeyConstraint("run_id", "step_no"),
        schema="core",
    )
    # Rows live for one step, so the default 20% threshold leaves dead tuples in
    # a hot queue far too long (ADR-0019:31). Storage parameters have no
    # SQLAlchemy table argument, so they are set after the create.
    op.execute(
        "ALTER TABLE core.step_queue SET ("
        "autovacuum_vacuum_scale_factor = 0.02,"
        " autovacuum_vacuum_threshold = 50)"
    )
    op.create_table(
        "mailbox_message",
        sa.Column("id", UUID, primary_key=True),
        _org_id("mailbox_message"),
        _run_id("mailbox_message"),
        sa.Column("seq", sa.Integer, nullable=False),
        sa.Column("kind", sa.Text, nullable=False),
        sa.Column(
            "author_principal_id",
            UUID,
            sa.ForeignKey(
                "core.principal.id", name="fk_mailbox_message_principal"
            ),
            nullable=False,
        ),
        sa.Column("body", JSONB, nullable=False),
        _created_at(),
        sa.CheckConstraint(
            "kind IN ('steer', 'conflict', 'context_lost')",
            name="ck_mailbox_message_kind",
        ),
        sa.UniqueConstraint("run_id", "seq", name="uq_mailbox_message_run_seq"),
        schema="core",
    )
    op.create_table(
        "checkpoint",
        sa.Column("id", UUID, primary_key=True),
        _org_id("checkpoint"),
        _run_id("checkpoint"),
        sa.Column("step_no", sa.Integer, nullable=False),
        sa.Column("state", JSONB, nullable=False),
        _created_at(),
        schema="core",
    )
    op.create_table(
        "context_manifest",
        sa.Column("id", UUID, primary_key=True),
        _org_id("context_manifest"),
        _run_id("context_manifest"),
        sa.Column("step_no", sa.Integer, nullable=False),
        sa.Column("prefix_key", sa.Text, nullable=False),
        sa.Column("layers", JSONB, nullable=False),
        sa.Column("token_cost", sa.Integer, nullable=False),
        sa.Column("cache_positions", JSONB, nullable=False),
        sa.Column("telemetry", JSONB, nullable=False),
        sa.Column("effective_scope", JSONB, nullable=False),
        _created_at(),
        schema="core",
    )
    op.create_table(
        "usage_record",
        sa.Column("id", UUID, primary_key=True),
        _org_id("usage_record"),
        _run_id("usage_record"),
        sa.Column("step_no", sa.Integer, nullable=False),
        _tier("usage_record"),
        sa.Column("input_tokens", sa.Integer, nullable=False),
        sa.Column("output_tokens", sa.Integer, nullable=False),
        sa.Column("cached_tokens", sa.Integer, nullable=False),
        _created_at(),
        schema="core",
    )

    for schema, table in TENANT_TABLES:
        key = "id" if table == "org" else "org_id"
        predicate = f"{key} = current_setting('app.org_id', true)::uuid"
        op.execute(f'ALTER TABLE {schema}."{table}" ENABLE ROW LEVEL SECURITY')
        op.execute(f'ALTER TABLE {schema}."{table}" FORCE ROW LEVEL SECURITY')
        op.execute(
            f'CREATE POLICY rls_{table} ON {schema}."{table}" FOR ALL '
            f"TO {APP_ROLE}, {LEDGER_ROLE} "
            f"USING ({predicate}) WITH CHECK ({predicate})"
        )
        if table in APPEND_ONLY:
            op.execute(f'GRANT SELECT ON {schema}."{table}" TO {APP_ROLE}')
            op.execute(f'GRANT INSERT ON {schema}."{table}" TO {LEDGER_ROLE}')
        else:
            op.execute(
                f'GRANT SELECT, INSERT, UPDATE, DELETE ON {schema}."{table}"'
                f" TO {APP_ROLE}"
            )
    for table in LEDGER_WRITABLE:
        op.execute(
            f'GRANT SELECT, INSERT, UPDATE ON core."{table}" TO {LEDGER_ROLE}'
        )
    for schema, table in GLOBAL_TABLES:
        op.execute(f"GRANT SELECT ON {schema}.{table} TO {APP_ROLE}, {LEDGER_ROLE}")
    op.execute(f"GRANT INSERT ON core.operation_version TO {APP_ROLE}")
    # The tier names are fixed; the bindings under them are edited at runtime.
    op.execute(f"GRANT INSERT, UPDATE ON core.tier, core.tier_binding TO {APP_ROLE}")


def downgrade() -> None:
    for schema, table in reversed(CREATE_ORDER):
        op.drop_table(table, schema=schema)
    op.execute("DROP SCHEMA mod_skills")
    op.execute("DROP SCHEMA core")
    op.execute(f"DROP ROLE IF EXISTS {LEDGER_ROLE}")
    op.execute(f"DROP ROLE IF EXISTS {APP_ROLE}")
