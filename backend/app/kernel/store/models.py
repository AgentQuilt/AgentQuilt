"""The spine tables mapped, column for column with migration 0001.

Written out rather than reflected, so a drift between the mapping and the chain
fails `test_models_match_migration` instead of surfacing at runtime. No
relationships: the session is scoped to one org, and a join is written where it
is needed. `mod_skills`' two tables are here rather than under `modules/skills`
so that `core.run`'s foreign key resolves inside one metadata and neither the
`skills` context contributor nor `runs.create` has to import a buildable module;
what is done with them is that module's (`app/modules/skills/MODULE.md`).
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    ForeignKey,
    ForeignKeyConstraint,
    Integer,
    MetaData,
    PrimaryKeyConstraint,
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


def created_at_column() -> Mapped[datetime]:
    """The one `created_at` mapping; model files import it, never re-declare it."""
    return mapped_column(TIMESTAMP(timezone=True), server_default=NOW)


# The plane a row belongs to, taken from the session's GUC by the database
# itself: no writer plumbs it, and an insert from a session that never set the
# GUC fails on the cast, which is what fails writes closed the way RLS fails
# reads. Model files import these three, never re-declare them.
PLANE = text("current_setting('app.environment_id')::uuid")


def environment_id_column() -> Mapped[UUID]:
    """The plane key every env-scoped table carries."""
    return mapped_column(server_default=PLANE)


def environment_scope(table: str) -> ForeignKeyConstraint:
    """The pair, onto `core.environment`: a row cannot name another org's plane."""
    return ForeignKeyConstraint(
        ["org_id", "environment_id"],
        ["core.environment.org_id", "core.environment.id"],
        name=f"fk_{table}_environment",
    )


def scope_fk(
    table: str, column: str, parent: str, *, deferred: bool = False
) -> ForeignKeyConstraint:
    """One env-scoped row's reference to another, carrying the scope with it, so
    no row can point across planes (ADR-0028 D2)."""
    return ForeignKeyConstraint(
        ["org_id", "environment_id", column],
        [
            f"core.{parent}.org_id",
            f"core.{parent}.environment_id",
            f"core.{parent}.id",
        ],
        name=f"fk_{table}_{column.removesuffix('_id')}_scope",
        use_alter=True,
        deferrable=True if deferred else None,
        initially="DEFERRED" if deferred else None,
    )


def scope_parent(table: str) -> UniqueConstraint:
    """What a scope-carrying key points at; the primary key alone is not unique
    over the triple, and Postgres requires that it is."""
    return UniqueConstraint(
        "org_id", "environment_id", "id", name=f"uq_{table}_org_environment_id"
    )


class Org(Base):
    __tablename__ = "org"

    id: Mapped[UUID] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = created_at_column()


class Environment(Base):
    """One plane of one org: where activity happens, and what a session pins.

    The lookup table for the plane, so its own row-level security stays keyed on
    the org alone — a session has to read it to know which plane it is on.
    """

    __tablename__ = "environment"
    __table_args__ = (
        CheckConstraint("kind IN ('dev', 'prod')", name="ck_environment_kind"),
        UniqueConstraint("org_id", "key", name="uq_environment_org_key"),
        # What every scope-carrying foreign key points at; the primary key alone
        # does not make the pair unique, and Postgres requires that it is.
        UniqueConstraint("org_id", "id", name="uq_environment_org_id"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True)
    org_id: Mapped[UUID] = mapped_column(
        ForeignKey("core.org.id", name="fk_environment_org")
    )
    key: Mapped[str] = mapped_column(Text)
    kind: Mapped[str] = mapped_column(Text)
    protection_level: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = created_at_column()


class User(Base):
    __tablename__ = "user"

    id: Mapped[UUID] = mapped_column(primary_key=True)
    org_id: Mapped[UUID] = mapped_column(ForeignKey("core.org.id", name="fk_user_org"))
    display_name: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = created_at_column()


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
    created_at: Mapped[datetime] = created_at_column()


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
    created_at: Mapped[datetime] = created_at_column()


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
    created_at: Mapped[datetime] = created_at_column()
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
        environment_scope("run"),
        scope_parent("run"),
        scope_fk("run", "parent_id", "run"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True)
    parent_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("core.run.id", name="fk_run_parent")
    )
    org_id: Mapped[UUID] = mapped_column(ForeignKey("core.org.id", name="fk_run_org"))
    environment_id: Mapped[UUID] = environment_id_column()
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
    created_at: Mapped[datetime] = created_at_column()
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
    created_at: Mapped[datetime] = created_at_column()


class SkillBinding(Base):
    """Which version of one skill one plane runs: the pointer promotion flips."""

    __tablename__ = "skill_binding"
    __table_args__ = (
        PrimaryKeyConstraint("org_id", "environment_id", "skill_id"),
        ForeignKeyConstraint(
            ["org_id", "environment_id"],
            ["core.environment.org_id", "core.environment.id"],
            name="fk_skill_binding_environment",
        ),
        ForeignKeyConstraint(
            ["skill_id", "skill_version_id"],
            ["mod_skills.skill_version.skill_id", "mod_skills.skill_version.id"],
            name="fk_skill_binding_skill_version",
        ),
        {"schema": "mod_skills"},
    )

    org_id: Mapped[UUID] = mapped_column(
        ForeignKey("core.org.id", name="fk_skill_binding_org")
    )
    environment_id: Mapped[UUID] = mapped_column()
    skill_id: Mapped[UUID] = mapped_column(
        ForeignKey("mod_skills.skill.id", name="fk_skill_binding_skill")
    )
    skill_version_id: Mapped[str] = mapped_column(Text)
