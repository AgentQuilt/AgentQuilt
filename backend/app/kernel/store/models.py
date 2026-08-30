"""The five spine tables mapped, column for column with migration 0001.

Written out rather than reflected, so a drift between the mapping and the chain
fails `test_models_match_migration` instead of surfacing at runtime. No
relationships: the session is scoped to one org, and a join is written where it
is needed.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    ForeignKey,
    Integer,
    MetaData,
    TIMESTAMP,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

NOW = text("now()")


class Base(DeclarativeBase):
    metadata = MetaData(schema="core")


def _created_at() -> Mapped[datetime]:
    return mapped_column(TIMESTAMP(timezone=True), server_default=NOW)


class Org(Base):
    __tablename__ = "org"

    id: Mapped[UUID] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = _created_at()


class User(Base):
    __tablename__ = "user"

    id: Mapped[UUID] = mapped_column(primary_key=True)
    org_id: Mapped[UUID] = mapped_column(ForeignKey("core.org.id", name="fk_user_org"))
    display_name: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = _created_at()


class Principal(Base):
    __tablename__ = "principal"
    __table_args__ = (
        CheckConstraint(
            "\"class\" IN ('user', 'agent', 'run', 'system', 'external')",
            name="ck_principal_class",
        ),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True)
    org_id: Mapped[UUID] = mapped_column(
        ForeignKey("core.org.id", name="fk_principal_org")
    )
    # `class` is a keyword; the column keeps the name the migration gives it.
    class_: Mapped[str] = mapped_column("class", Text)
    user_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("core.user.id", name="fk_principal_user")
    )
    created_at: Mapped[datetime] = _created_at()


class AgentDefinition(Base):
    __tablename__ = "agent_definition"
    __table_args__ = (
        UniqueConstraint(
            "org_id", "name", "version", name="uq_agent_definition_org_name_version"
        ),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True)
    org_id: Mapped[UUID] = mapped_column(
        ForeignKey("core.org.id", name="fk_agent_definition_org")
    )
    name: Mapped[str] = mapped_column(Text)
    version: Mapped[int] = mapped_column(Integer)
    soul_text: Mapped[str] = mapped_column(Text)
    tier: Mapped[str] = mapped_column(Text)
    budget_cap_tokens: Mapped[int] = mapped_column(Integer)
    memory_scope: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = _created_at()


class UserToken(Base):
    __tablename__ = "user_token"
    __table_args__ = (UniqueConstraint("token_hash", name="uq_user_token_token_hash"),)

    id: Mapped[UUID] = mapped_column(primary_key=True)
    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("core.user.id", name="fk_user_token_user")
    )
    org_id: Mapped[UUID] = mapped_column(
        ForeignKey("core.org.id", name="fk_user_token_org")
    )
    token_hash: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = _created_at()
    revoked_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))
