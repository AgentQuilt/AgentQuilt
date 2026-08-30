"""The three run-loop tables mapped, column for column with migration 0001.

On the store's `Base`, so there is one metadata and `test_models_match_migration`
reads these too. `core.run` is already mapped in `store.models`; it is read from
there, never mapped twice.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    ForeignKey,
    Integer,
    PrimaryKeyConstraint,
    TIMESTAMP,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.kernel.store.models import Base, Json, created_at_column


class StepQueue(Base):
    """One row per step waiting to be worked; the lease is who holds it now."""

    __tablename__ = "step_queue"
    __table_args__ = (PrimaryKeyConstraint("run_id", "step_no"),)

    org_id: Mapped[UUID] = mapped_column(
        ForeignKey("core.org.id", name="fk_step_queue_org")
    )
    run_id: Mapped[UUID] = mapped_column(
        ForeignKey("core.run.id", name="fk_step_queue_run")
    )
    step_no: Mapped[int] = mapped_column(Integer)
    queue_tag: Mapped[str] = mapped_column(Text)
    lease_until: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))
    claimed_by: Mapped[str | None] = mapped_column(Text)


class MailboxMessage(Base):
    """One message steered into a live run; `seq` is its order in the mailbox."""

    __tablename__ = "mailbox_message"
    __table_args__ = (
        CheckConstraint(
            "kind IN ('steer', 'conflict', 'context_lost')",
            name="ck_mailbox_message_kind",
        ),
        UniqueConstraint("run_id", "seq", name="uq_mailbox_message_run_seq"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True)
    org_id: Mapped[UUID] = mapped_column(
        ForeignKey("core.org.id", name="fk_mailbox_message_org")
    )
    run_id: Mapped[UUID] = mapped_column(
        ForeignKey("core.run.id", name="fk_mailbox_message_run")
    )
    seq: Mapped[int] = mapped_column(Integer)
    kind: Mapped[str] = mapped_column(Text)
    author_principal_id: Mapped[UUID] = mapped_column(
        ForeignKey("core.principal.id", name="fk_mailbox_message_principal")
    )
    body: Mapped[Json] = mapped_column(JSONB)
    created_at: Mapped[datetime] = created_at_column()


class Checkpoint(Base):
    """What one finished step left behind, for the next step to resume from."""

    __tablename__ = "checkpoint"

    id: Mapped[UUID] = mapped_column(primary_key=True)
    org_id: Mapped[UUID] = mapped_column(
        ForeignKey("core.org.id", name="fk_checkpoint_org")
    )
    run_id: Mapped[UUID] = mapped_column(
        ForeignKey("core.run.id", name="fk_checkpoint_run")
    )
    step_no: Mapped[int] = mapped_column(Integer)
    state: Mapped[Json] = mapped_column(JSONB)
    created_at: Mapped[datetime] = created_at_column()
