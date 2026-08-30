"""Bind every operation-commit event to its action, in both directions.

Revision ID: 0002
Revises: 0001
Create Date: 2026-08-30

`action.event_id` already points back at the event. This adds the other half:
`event.action_id`, a CHECK that makes the pair exact (an operation_commit event
has an action, no other kind does), and a DEFERRABLE INITIALLY DEFERRED foreign
key, so one transaction can insert the event with a client-generated action id
and the action with the event's id, in that order, and settle at COMMIT.

It also gives the ledger writer SELECT on the two append-only tables: the writer
inserts them with RETURNING (the identity id the action and stream_head point at),
and Postgres reads RETURNING as a read, so INSERT alone is not enough.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.add_column(
        "event",
        sa.Column("action_id", postgresql.UUID(as_uuid=True), nullable=True),
        schema="core",
    )
    op.create_foreign_key(
        "fk_event_action",
        "event",
        "action",
        ["action_id"],
        ["id"],
        source_schema="core",
        referent_schema="core",
        deferrable=True,
        initially="DEFERRED",
    )
    op.create_check_constraint(
        "ck_event_action_id_by_kind",
        "event",
        "(kind = 'operation_commit') = (action_id IS NOT NULL)",
        schema="core",
    )
    # Reading is not writing: the append-only grants stand, and the row-level
    # policy scopes this SELECT to the session's org exactly as the app role's.
    op.execute(
        "GRANT SELECT ON core.event, core.action TO agentquilt_ledger_writer"
    )


def downgrade() -> None:
    op.execute(
        "REVOKE SELECT ON core.event, core.action FROM agentquilt_ledger_writer"
    )
    op.drop_constraint(
        "ck_event_action_id_by_kind", "event", type_="check", schema="core"
    )
    op.drop_constraint("fk_event_action", "event", type_="foreignkey", schema="core")
    op.drop_column("event", "action_id", schema="core")
