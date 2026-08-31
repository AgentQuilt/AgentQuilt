"""Lay the environment rail: the Environment row, the scope column, scope-carrying keys.

Revision ID: 0003
Revises: 0002
Create Date: 2026-08-31

Expand-only (ADR-0028 D2). Every env-scoped table gains a nullable
`environment_id`, backfilled to its org's prod plane; nothing is made NOT NULL
and no policy changes, because the session does not set `app.environment_id`
until migration 0004 — flipping either before that would lock out every writer
running today.

The pair (org_id, environment_id) is a composite foreign key onto
`core.environment (org_id, id)`, so a row cannot name a plane of another org;
every reference between two env-scoped rows carries the pair too, onto the
parent's new UNIQUE (org_id, environment_id, id), so no row points across
planes. `run.stage` and `skill_version.stage` stay: the code still reads them.
"""

from __future__ import annotations

from typing import Any

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | None = None
depends_on: str | None = None

UUID = postgresql.UUID(as_uuid=True)

APP_ROLE = "agentquilt_app"
LEDGER_ROLE = "agentquilt_ledger_writer"

# The eleven tables whose rows belong to one plane: activity, not content.
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
# Env-scoped rows another env-scoped row points at; they gain the referenced
# triple UNIQUE (org_id, environment_id, id) the composite keys below need.
ENV_SCOPED_PARENTS = ("run", "event", "action")

# (table, local column, parent table, deferred) — every reference between two
# env-scoped rows, as a scope-carrying key. These are added beside the
# single-column keys that exist today rather than replacing them: a composite
# key is MATCH SIMPLE, so it is not checked at all while `environment_id` is
# still NULL, and dropping the old key here would leave today's writers
# unconstrained for the whole expand window. 0004 drops the old keys when the
# column is NOT NULL, which is the contract half of the same move.
SCOPE_FK = (
    ("step_queue", "run_id", "run", False),
    ("mailbox_message", "run_id", "run", False),
    ("checkpoint", "run_id", "run", False),
    ("context_manifest", "run_id", "run", False),
    ("usage_record", "run_id", "run", False),
    # The journal's nullable run reference carried no key in 0001; on the rail
    # it is scope-carrying like approval's.
    ("event", "run_id", "run", False),
    ("run", "parent_id", "run", False),
    ("action", "event_id", "event", False),
    # The 0002 pairing settles at COMMIT, in both directions.
    ("event", "action_id", "action", True),
    ("stream_head", "last_event_id", "event", False),
    ("idempotency_key", "action_id", "action", False),
    # Approval's two references carry no key today; on the rail they are
    # scope-carrying like the rest.
    ("approval", "run_id", "run", False),
    ("approval", "consumed_by_action_id", "action", False),
)

# Two planes per org (ADR-0028 D2's small-org default); prod is the protected
# one. A third plane is an insert, not a migration.
PLANES = (("dev", 0), ("prod", 1))


def _environment_id() -> sa.Column[Any]:
    """The plane key. Nullable here; 0004 makes it NOT NULL once writers set it."""
    return sa.Column("environment_id", UUID, nullable=True)


def _scope_fk_name(table: str, column: str) -> str:
    return f"fk_{table}_{column.removesuffix('_id')}_scope"


def _enable_org_rls(schema: str, table: str) -> None:
    """The single-key org policy and app-role DML every tenant table carries."""
    predicate = "org_id = current_setting('app.org_id', true)::uuid"
    op.execute(f"ALTER TABLE {schema}.{table} ENABLE ROW LEVEL SECURITY")
    op.execute(f"ALTER TABLE {schema}.{table} FORCE ROW LEVEL SECURITY")
    op.execute(
        f"CREATE POLICY rls_{table} ON {schema}.{table} FOR ALL "
        f"TO {APP_ROLE}, {LEDGER_ROLE} "
        f"USING ({predicate}) WITH CHECK ({predicate})"
    )
    op.execute(
        f"GRANT SELECT, INSERT, UPDATE, DELETE ON {schema}.{table} TO {APP_ROLE}"
    )


def upgrade() -> None:
    op.create_table(
        "environment",
        sa.Column("id", UUID, primary_key=True),
        sa.Column(
            "org_id",
            UUID,
            sa.ForeignKey("core.org.id", name="fk_environment_org"),
            nullable=False,
        ),
        sa.Column("key", sa.Text, nullable=False),
        sa.Column("kind", sa.Text, nullable=False),
        sa.Column("protection_level", sa.Integer, nullable=False),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.CheckConstraint("kind IN ('dev', 'prod')", name="ck_environment_kind"),
        sa.UniqueConstraint("org_id", "key", name="uq_environment_org_key"),
        # The pair every scope-carrying foreign key below points at; Postgres
        # requires a referenced pair to be unique, which the primary key alone
        # does not make it.
        sa.UniqueConstraint("org_id", "id", name="uq_environment_org_id"),
        schema="core",
    )
    _enable_org_rls("core", "environment")

    for schema, table in ENV_SCOPED:
        op.add_column(table, _environment_id(), schema=schema)
    # Pinned by code in wave E2; the column lands with the rest of the rail.
    op.add_column(
        "run",
        sa.Column("tier_binding_version", sa.Integer, nullable=True),
        schema="core",
    )

    # Backfill, in DML the Alembic helpers do not express: two planes per org,
    # then every row that exists today onto its org's prod plane.
    op.execute(
        "INSERT INTO core.environment (id, org_id, key, kind, protection_level)"
        " SELECT gen_random_uuid(), o.id, p.key, p.key, p.protection"
        " FROM core.org o"
        " CROSS JOIN (VALUES " + ", ".join(f"('{k}', {n})" for k, n in PLANES) + ")"
        " AS p(key, protection)"
    )
    for schema, table in ENV_SCOPED:
        op.execute(
            f"UPDATE {schema}.{table} AS t SET environment_id = e.id"
            " FROM core.environment e"
            " WHERE e.org_id = t.org_id AND e.kind = 'prod'"
        )

    for schema, table in ENV_SCOPED:
        op.create_foreign_key(
            f"fk_{table}_environment",
            table,
            "environment",
            ["org_id", "environment_id"],
            ["org_id", "id"],
            source_schema=schema,
            referent_schema="core",
        )
    for table in ENV_SCOPED_PARENTS:
        op.create_unique_constraint(
            f"uq_{table}_org_environment_id",
            table,
            ["org_id", "environment_id", "id"],
            schema="core",
        )
    for table, column, parent, deferred in SCOPE_FK:
        op.create_foreign_key(
            _scope_fk_name(table, column),
            table,
            parent,
            ["org_id", "environment_id", column],
            ["org_id", "environment_id", "id"],
            source_schema="core",
            referent_schema="core",
            deferrable=True if deferred else None,
            initially="DEFERRED" if deferred else None,
        )

    # A binding names one skill's version, never another's, so the reference is
    # the pair — which needs this second unique key on the version table.
    op.create_unique_constraint(
        "uq_skill_version_skill_id",
        "skill_version",
        ["skill_id", "id"],
        schema="mod_skills",
    )
    op.create_table(
        "skill_binding",
        sa.Column(
            "org_id",
            UUID,
            sa.ForeignKey("core.org.id", name="fk_skill_binding_org"),
            nullable=False,
        ),
        sa.Column("environment_id", UUID, nullable=False),
        sa.Column(
            "skill_id",
            UUID,
            sa.ForeignKey("mod_skills.skill.id", name="fk_skill_binding_skill"),
            nullable=False,
        ),
        sa.Column("skill_version_id", sa.Text, nullable=False),
        # One active version per skill per plane: the pointer ADR-0028 D5 flips.
        sa.PrimaryKeyConstraint("org_id", "environment_id", "skill_id"),
        sa.ForeignKeyConstraint(
            ["org_id", "environment_id"],
            ["core.environment.org_id", "core.environment.id"],
            name="fk_skill_binding_environment",
        ),
        sa.ForeignKeyConstraint(
            ["skill_id", "skill_version_id"],
            ["mod_skills.skill_version.skill_id", "mod_skills.skill_version.id"],
            name="fk_skill_binding_skill_version",
        ),
        schema="mod_skills",
    )
    _enable_org_rls("mod_skills", "skill_binding")
    # Backfill from the stage column the bindings replace: PROD to the prod
    # plane, DEV and QA to the dev plane; where several versions of one skill
    # share a plane the greatest id wins and the losers stay unbound, so the
    # result is the same on any deployment.
    op.execute(
        "INSERT INTO mod_skills.skill_binding"
        " (org_id, environment_id, skill_id, skill_version_id)"
        " SELECT DISTINCT ON (v.org_id, e.id, v.skill_id)"
        " v.org_id, e.id, v.skill_id, v.id"
        " FROM mod_skills.skill_version v"
        " JOIN core.environment e ON e.org_id = v.org_id"
        " AND e.kind = CASE WHEN v.stage = 'PROD' THEN 'prod' ELSE 'dev' END"
        " ORDER BY v.org_id, e.id, v.skill_id, v.id DESC"
    )


def downgrade() -> None:
    op.drop_table("skill_binding", schema="mod_skills")
    op.drop_constraint(
        "uq_skill_version_skill_id",
        "skill_version",
        type_="unique",
        schema="mod_skills",
    )

    for table, column, _parent, _deferred in SCOPE_FK:
        op.drop_constraint(
            _scope_fk_name(table, column), table, type_="foreignkey", schema="core"
        )
    for table in ENV_SCOPED_PARENTS:
        op.drop_constraint(
            f"uq_{table}_org_environment_id", table, type_="unique", schema="core"
        )
    for schema, table in ENV_SCOPED:
        op.drop_constraint(
            f"fk_{table}_environment", table, type_="foreignkey", schema=schema
        )

    op.drop_column("run", "tier_binding_version", schema="core")
    for schema, table in ENV_SCOPED:
        op.drop_column(table, "environment_id", schema=schema)
    op.drop_table("environment", schema="core")
