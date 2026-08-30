"""Fixture kit shared by the kernel modules' own test folders."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.kernel.ports.context_contributor import (
    EnvelopeSlot,
    Layer,
    PrefixSlot,
    Scope as PrefixScope,
    Slice,
    Turn,
)
from app.kernel.store.seed import seed

# An org and the principal acting in it: what every scoped session is opened with.
Scope = tuple[UUID, UUID]

START = datetime(2026, 1, 1, tzinfo=UTC)


async def two_principals(url: str) -> tuple[Scope, Scope]:
    """Seed two orgs and hand back their system principals, one scope each."""
    first, second = await seed()
    return (
        (first.org_id, first.system_principal_id),
        (second.org_id, second.system_principal_id),
    )


class FakeClock:
    """The kernel reads time through one injected `Callable[[], datetime]`."""

    def __init__(self) -> None:
        self._now = START

    def now(self) -> datetime:
        return self._now

    def advance(self, seconds: float) -> None:
        self._now += timedelta(seconds=seconds)


class StaticContributor:
    """Scripted layers and slices, for a test whose point is the assembly rather
    than a store. One object satisfies both contracts, which is what the `skills`
    adapter does for real."""

    def __init__(
        self, owner: str, layers: tuple[Layer, ...], slices: tuple[Slice, ...]
    ) -> None:
        self.owner = owner
        self.prefix_slots: tuple[PrefixSlot, ...] = tuple(one.slot for one in layers)
        self.envelope_slots: tuple[EnvelopeSlot, ...] = tuple(
            one.slot for one in slices
        )
        self._layers = layers
        self._slices = slices

    async def fetch(
        self, session: AsyncSession, scope: PrefixScope
    ) -> tuple[Layer, ...]:
        return self._layers

    def layers(self, source: tuple[Layer, ...]) -> tuple[Layer, ...]:
        return source

    async def slices(
        self, session: AsyncSession, scope: PrefixScope, turn: Turn
    ) -> tuple[Slice, ...]:
        return self._slices
