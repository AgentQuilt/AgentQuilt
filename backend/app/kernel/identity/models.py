"""The two permission tables mapped, column for column with migration 0001.

On the store's `Base`, so there is one metadata and `test_models_match_migration`
reads these too. Written out rather than reflected, for the reason store/models.py
gives. No relationships: a join is written where it is needed.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    ForeignKey,
    Index,
    Integer,
    TIMESTAMP,
    Text,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.kernel.store.models import Base

NOW = text("now()")


def _org_id(table: str) -> Mapped[UUID]:
    return mapped_column(ForeignKey("core.org.id", name=f"fk_{table}_org"))


class Grant(Base):
    """What one principal may do with one operation: the whole permission state."""

    __tablename__ = "grant"
    __table_args__ = (
        CheckConstraint(
            "level IN ('may_use', 'asks_first', 'never')", name="ck_grant_level"
        ),
        CheckConstraint(
            "scope_form IN ('entity', 'node_plus_descendants', 'all_of_type')",
            name="ck_grant_scope_form",
        ),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True)
    org_id: Mapped[UUID] = _org_id("grant")
    principal_id: Mapped[UUID] = mapped_column(
        ForeignKey("core.principal.id", name="fk_grant_principal")
    )
    operation_name: Mapped[str] = mapped_column(Text)
    level: Mapped[str] = mapped_column(Text)
    scope_form: Mapped[str] = mapped_column(Text, server_default=text("'entity'"))
    scope_ref: Mapped[str | None] = mapped_column(Text)


class Approval(Base):
    """One human decision, bound to one call: scoped, expiring, consumed once."""

    __tablename__ = "approval"
    __table_args__ = (
        CheckConstraint(
            "state IN ('requested', 'open', 'consumed', 'rejected', 'expired',"
            " 'superseded')",
            name="ck_approval_state",
        ),
        Index("ix_approval_org_state", "org_id", "state"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True)
    org_id: Mapped[UUID] = _org_id("approval")
    granted_to: Mapped[UUID] = mapped_column(
        ForeignKey("core.principal.id", name="fk_approval_granted_to")
    )
    granted_by: Mapped[UUID | None] = mapped_column(
        ForeignKey("core.principal.id", name="fk_approval_granted_by")
    )
    operation_version_id: Mapped[str] = mapped_column(
        Text,
        ForeignKey("core.operation_version.id", name="fk_approval_operation_version"),
    )
    args_hash: Mapped[str] = mapped_column(Text)
    state: Mapped[str] = mapped_column(Text)
    reason: Mapped[str | None] = mapped_column(Text)
    # The continuation: the parked call resumes under exactly this triple.
    run_id: Mapped[UUID] = mapped_column()
    step_no: Mapped[int] = mapped_column(Integer)
    tool_call_id: Mapped[str] = mapped_column(Text)
    expires_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True))
    consumed_by_action_id: Mapped[UUID | None] = mapped_column()
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=NOW
    )
