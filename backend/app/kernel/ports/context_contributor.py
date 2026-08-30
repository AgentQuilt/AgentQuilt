from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Protocol
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

# L0 (platform policy) and L5 (tools block) are kernel-owned and never cross
# the seam (ADR-0013). D2 does not exist (ADR-0013).
PrefixSlot = Literal["L1", "L2", "L3", "L4", "L6"]
EnvelopeSlot = Literal["D1", "D3", "D4", "D5", "D6"]
PrefixProfile = Literal["personal", "space", "none"]


@dataclass(frozen=True, slots=True)
class Scope:
    """Who the run is for. Deliberately no run or step: a prefix rendered from
    this alone cannot depend on the turn."""

    agent_definition_id: UUID
    principal_id: UUID
    prefix_profile: PrefixProfile
    surface: str


@dataclass(frozen=True, slots=True)
class Turn:
    """The per-turn identity; an envelope adapter reads the rest via the session."""

    run_id: UUID
    step_no: int


@dataclass(frozen=True, slots=True)
class Layer:
    """One prefix layer. The version is the layer's term in prefix_key; under the
    `none` profile L3's version is the profile term and the body is empty
    (ADR-0016). Token cost is measured by `context`, not declared here."""

    slot: PrefixSlot
    version: str
    body: str


@dataclass(frozen=True, slots=True)
class Slice:
    """One envelope contribution; dropped by priority when over budget, and the
    provenance (a version id or ref) lands in the manifest."""

    slot: EnvelopeSlot
    body: str
    provenance: str
    priority: int


class PrefixContributor[SourceT](Protocol):
    """The stable half. `fetch` takes no Turn, so per-turn state cannot
    reach prefix code; `layers` is sync over the fetched value, so it cannot
    await, reach the session, or see the turn. Determinism beyond that is the
    property test's job, not the signature's."""

    owner: str
    prefix_slots: tuple[PrefixSlot, ...]

    async def fetch(self, session: AsyncSession, scope: Scope) -> SourceT: ...

    def layers(self, source: SourceT) -> tuple[Layer, ...]: ...


class EnvelopeContributor(Protocol):
    """The per-turn half; free to read whatever the session reaches."""

    owner: str
    envelope_slots: tuple[EnvelopeSlot, ...]

    async def slices(
        self, session: AsyncSession, scope: Scope, turn: Turn
    ) -> tuple[Slice, ...]: ...
