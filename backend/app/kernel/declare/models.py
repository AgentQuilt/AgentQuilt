"""The ledger tables mapped, column for column with migrations 0001 and 0002.

On the store's `Base`, so there is one metadata and `test_models_match_migration`
reads these too. Written out rather than reflected, for the reason store/models.py
gives. No relationships: a join is written where it is needed.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    ForeignKey,
    Identity,
    Index,
    Integer,
    PrimaryKeyConstraint,
    TIMESTAMP,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.kernel.store.models import (
    Base,
    Json,
    environment_id_column,
    environment_scope,
    scope_fk,
    scope_parent,
)

NOW = text("now()")


def _created_at() -> Mapped[datetime]:
    return mapped_column(TIMESTAMP(timezone=True), server_default=NOW)


def _org_id(table: str) -> Mapped[UUID]:
    return mapped_column(ForeignKey("core.org.id", name=f"fk_{table}_org"))


class Event(Base):
    """Append-only, written only under `agentquilt_ledger_writer`."""

    __tablename__ = "event"
    __table_args__ = (
        CheckConstraint(
            "kind IN ('operation_commit', 'run_journal', 'read_audit', 'denial')",
            name="ck_event_kind",
        ),
        CheckConstraint(
            "(kind = 'operation_commit') = (action_id IS NOT NULL)",
            name="ck_event_action_id_by_kind",
        ),
        # One version per aggregate, counted over commits only: the other kinds
        # carry version 0 and would collide.
        Index(
            "uq_event_org_aggregate_version",
            "org_id",
            "aggregate_kind",
            "aggregate_id",
            "aggregate_version",
            unique=True,
            postgresql_where=text("kind = 'operation_commit'"),
        ),
        environment_scope("event"),
        scope_parent("event"),
        scope_fk("event", "run_id", "run"),
        # The 0002 pairing settles at COMMIT, in both directions.
        scope_fk("event", "action_id", "action", deferred=True),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    org_id: Mapped[UUID] = _org_id("event")
    environment_id: Mapped[UUID] = environment_id_column()
    kind: Mapped[str] = mapped_column(Text)
    aggregate_kind: Mapped[str] = mapped_column(Text)
    aggregate_id: Mapped[UUID] = mapped_column()
    aggregate_version: Mapped[int] = mapped_column(Integer)
    run_id: Mapped[UUID | None] = mapped_column()
    step_no: Mapped[int | None] = mapped_column(Integer)
    principal_id: Mapped[UUID] = mapped_column()
    operation_name: Mapped[str | None] = mapped_column(Text)
    payload: Mapped[Json] = mapped_column(JSONB)
    created_at: Mapped[datetime] = _created_at()
    # Deferred, so the commit inserts the event and then its action in one
    # transaction and the pair settles at COMMIT.
    action_id: Mapped[UUID | None] = mapped_column(
        ForeignKey(
            "core.action.id",
            name="fk_event_action",
            # event and action point at each other; this tells the metadata
            # which of the two edges to break when it sorts the tables.
            use_alter=True,
            deferrable=True,
            initially="DEFERRED",
        )
    )


class StreamHead(Base):
    """The current version of one aggregate; `expected_version` reads it."""

    __tablename__ = "stream_head"
    __table_args__ = (
        PrimaryKeyConstraint("org_id", "aggregate_kind", "aggregate_id"),
        environment_scope("stream_head"),
        scope_fk("stream_head", "last_event_id", "event"),
    )

    org_id: Mapped[UUID] = _org_id("stream_head")
    environment_id: Mapped[UUID] = environment_id_column()
    aggregate_kind: Mapped[str] = mapped_column(Text)
    aggregate_id: Mapped[UUID] = mapped_column()
    version: Mapped[int] = mapped_column(Integer)
    last_event_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("core.event.id", name="fk_stream_head_event")
    )


class OperationVersion(Base):
    """Deployment-global: no org_id, so no row-level security."""

    __tablename__ = "operation_version"
    __table_args__ = (
        CheckConstraint(
            "stage IN ('DEV', 'QA', 'PROD')", name="ck_operation_version_stage"
        ),
    )

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    operation_name: Mapped[str] = mapped_column(Text)
    stage: Mapped[str] = mapped_column(Text)
    declaration: Mapped[Json] = mapped_column(JSONB)
    created_at: Mapped[datetime] = _created_at()


class Action(Base):
    """One per operation-commit event, and never more (`uq_action_event`)."""

    __tablename__ = "action"
    __table_args__ = (
        UniqueConstraint("event_id", name="uq_action_event"),
        environment_scope("action"),
        scope_parent("action"),
        scope_fk("action", "event_id", "event"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True)
    org_id: Mapped[UUID] = _org_id("action")
    environment_id: Mapped[UUID] = environment_id_column()
    event_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("core.event.id", name="fk_action_event")
    )
    operation_version_id: Mapped[str] = mapped_column(
        Text,
        ForeignKey("core.operation_version.id", name="fk_action_operation_version"),
    )
    approval_id: Mapped[UUID | None] = mapped_column()
    idempotency_key: Mapped[str] = mapped_column(Text)
    decision_trace: Mapped[Json] = mapped_column(JSONB)
    compensator_ref: Mapped[str | None] = mapped_column(Text)
    compensator_args: Mapped[Json | None] = mapped_column(JSONB)
    external_attempt: Mapped[Json | None] = mapped_column(JSONB)
    external_observation: Mapped[Json | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = _created_at()


class IdempotencyKey(Base):
    """The retry key: its primary key is what makes a second commit a no-op."""

    __tablename__ = "idempotency_key"
    __table_args__ = (
        PrimaryKeyConstraint("org_id", "operation_name", "idempotency_key"),
        environment_scope("idempotency_key"),
        scope_fk("idempotency_key", "action_id", "action"),
    )

    org_id: Mapped[UUID] = _org_id("idempotency_key")
    environment_id: Mapped[UUID] = environment_id_column()
    operation_name: Mapped[str] = mapped_column(Text)
    idempotency_key: Mapped[str] = mapped_column(Text)
    action_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("core.action.id", name="fk_idempotency_key_action")
    )
