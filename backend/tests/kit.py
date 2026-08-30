"""Fixture kit shared by the kernel modules' own test folders."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID

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
