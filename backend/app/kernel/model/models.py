"""The binding and the usage row, mapped column for column with migration 0001.

On the store's `Base`, so there is one metadata and `test_models_match_migration`
reads this too. `core.tier` is already mapped in `store.models`; it is read from
there, never mapped twice.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import ForeignKey, Integer, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.kernel.store.models import (
    Base,
    created_at_column,
    environment_id_column,
    environment_scope,
    scope_fk,
)

class TierBinding(Base):
    """What a tier resolves to right now: a provider, a model and an effort.

    Deployment-global, like the tier it names, and versioned rather than edited
    in place, so a past run's prefix key stays explicable.
    """

    __tablename__ = "tier_binding"

    id: Mapped[UUID] = mapped_column(primary_key=True)
    tier: Mapped[str] = mapped_column(
        Text, ForeignKey("core.tier.name", name="fk_tier_binding_tier")
    )
    provider: Mapped[str] = mapped_column(Text)
    model: Mapped[str] = mapped_column(Text)
    # Not every provider takes an effort setting.
    effort: Mapped[str | None] = mapped_column(Text)
    version: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = created_at_column()


class UsageRecord(Base):
    """One row per model call: what the turn cost, against the run's budget cap."""

    __tablename__ = "usage_record"
    __table_args__ = (
        environment_scope("usage_record"),
        scope_fk("usage_record", "run_id", "run"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True)
    org_id: Mapped[UUID] = mapped_column(
        ForeignKey("core.org.id", name="fk_usage_record_org")
    )
    environment_id: Mapped[UUID] = environment_id_column()
    run_id: Mapped[UUID] = mapped_column()
    step_no: Mapped[int] = mapped_column(Integer)
    tier: Mapped[str] = mapped_column(
        Text, ForeignKey("core.tier.name", name="fk_usage_record_tier")
    )
    input_tokens: Mapped[int] = mapped_column(Integer)
    output_tokens: Mapped[int] = mapped_column(Integer)
    cached_tokens: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = created_at_column()
