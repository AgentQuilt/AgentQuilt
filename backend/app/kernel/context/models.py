"""The assembly manifest mapped, column for column with migration 0001.

On the store's `Base`, so there is one metadata and `test_models_match_migration`
reads this too.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import ForeignKey, Integer, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.kernel.store.models import Base, Json, created_at_column

class ContextManifest(Base):
    """One row per assembled turn: what went into the prompt and what it cost."""

    __tablename__ = "context_manifest"

    id: Mapped[UUID] = mapped_column(primary_key=True)
    org_id: Mapped[UUID] = mapped_column(
        ForeignKey("core.org.id", name="fk_context_manifest_org")
    )
    run_id: Mapped[UUID] = mapped_column(
        ForeignKey("core.run.id", name="fk_context_manifest_run")
    )
    step_no: Mapped[int] = mapped_column(Integer)
    prefix_key: Mapped[str] = mapped_column(Text)
    layers: Mapped[Json] = mapped_column(JSONB)
    token_cost: Mapped[int] = mapped_column(Integer)
    cache_positions: Mapped[Json] = mapped_column(JSONB)
    telemetry: Mapped[Json] = mapped_column(JSONB)
    effective_scope: Mapped[Json] = mapped_column(JSONB)
    created_at: Mapped[datetime] = created_at_column()
