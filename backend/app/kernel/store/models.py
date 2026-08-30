"""The spine tables mapped, column for column with migration 0001.

Written out rather than reflected, so a drift between the mapping and the chain
fails `test_models_match_migration` instead of surfacing at runtime. No
relationships: the session is scoped to one org, and a join is written where it
is needed. `mod_skills`' two tables are here rather than under a module so that
`core.run`'s foreign key resolves inside one metadata; they move when
`modules/skills` lands.
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
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

Json = dict[str, object]

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


class Tier(Base):
    """The four tier names ADR-0009 fixes, seeded by the migration. Global: no org."""

    __tablename__ = "tier"
    __table_args__ = (
        CheckConstraint(
            "name IN ('orchestrator', 'executor', 'simple', 'image')",
            name="ck_tier_name",
        ),
    )

    name: Mapped[str] = mapped_column(Text, primary_key=True)


class Run(Base):
    """One activation of an agent definition, and the row every step hangs off."""

    __tablename__ = "run"
    __table_args__ = (
        CheckConstraint(
            "state IN ('queued', 'running', 'waiting_approval', 'done',"
            " 'failed', 'cancelled')",
            name="ck_run_state",
        ),
        CheckConstraint(
            "prefix_profile IN ('personal', 'space', 'none')",
            name="ck_run_prefix_profile",
        ),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True)
    parent_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("core.run.id", name="fk_run_parent")
    )
    org_id: Mapped[UUID] = mapped_column(ForeignKey("core.org.id", name="fk_run_org"))
    agent_definition_id: Mapped[UUID] = mapped_column(
        ForeignKey("core.agent_definition.id", name="fk_run_agent_definition")
    )
    skill_version_id: Mapped[str | None] = mapped_column(
        Text, ForeignKey("mod_skills.skill_version.id", name="fk_run_skill_version")
    )
    stage: Mapped[str] = mapped_column(Text)
    state: Mapped[str] = mapped_column(Text)
    failure_reason: Mapped[str | None] = mapped_column(Text)
    budget_cap_tokens: Mapped[int] = mapped_column(Integer)
    prefix_key: Mapped[str] = mapped_column(Text)
    capability_ceiling: Mapped[Json] = mapped_column(JSONB)
    # Root runs only: a child narrows against its parent's state.
    narrowing_state: Mapped[Json | None] = mapped_column(JSONB)
    prefix_profile: Mapped[str] = mapped_column(Text)
    acting_external_principal_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("core.principal.id", name="fk_run_acting_external")
    )
    pinned_worker_id: Mapped[str | None] = mapped_column(Text)
    worker_heartbeat_at: Mapped[datetime | None] = mapped_column(
        TIMESTAMP(timezone=True)
    )
    created_at: Mapped[datetime] = _created_at()
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=NOW
    )


class Skill(Base):
    """One skill, by name; the directory L6 renders is these names."""

    __tablename__ = "skill"
    __table_args__ = {"schema": "mod_skills"}

    id: Mapped[UUID] = mapped_column(primary_key=True)
    org_id: Mapped[UUID] = mapped_column(
        ForeignKey("core.org.id", name="fk_skill_org")
    )
    name: Mapped[str] = mapped_column(Text)


class SkillVersion(Base):
    """One published body of a skill; the run's bound version is D1."""

    __tablename__ = "skill_version"
    __table_args__ = (
        CheckConstraint(
            "execution_mode IN ('inline', 'delegated')",
            name="ck_skill_version_execution_mode",
        ),
        {"schema": "mod_skills"},
    )

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    org_id: Mapped[UUID] = mapped_column(
        ForeignKey("core.org.id", name="fk_skill_version_org")
    )
    skill_id: Mapped[UUID] = mapped_column(
        ForeignKey("mod_skills.skill.id", name="fk_skill_version_skill")
    )
    tier: Mapped[str] = mapped_column(
        Text, ForeignKey("core.tier.name", name="fk_skill_version_tier")
    )
    execution_mode: Mapped[str] = mapped_column(Text)
    operations: Mapped[Json] = mapped_column(JSONB)
    stage: Mapped[str] = mapped_column(Text)
    body: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = _created_at()
