"""Fixture kit shared by the kernel modules' own test folders."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID

from pydantic_ai import models
from pydantic_ai.direct import model_request
from pydantic_ai.messages import ModelRequest, UserPromptPart
from pydantic_ai.models import ModelRequestParameters
from pydantic_ai.models.function import FunctionDef, FunctionModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.kernel.context.service import AssembledTurn
from app.kernel.model.adapter import completion, instructions, tool_definitions
from app.kernel.ports.context_contributor import (
    EnvelopeSlot,
    Layer,
    PrefixSlot,
    Scope as PrefixScope,
    Slice,
    Turn,
)
from app.kernel.ports.model_runner import Binding, Completion
from app.kernel.store.seed import seed

# No test in this suite may reach a provider; the fake below goes through
# `FunctionModel`, which this flag does not gate.
models.ALLOW_MODEL_REQUESTS = False

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


class FakeModelRunner:
    """`ModelRunner` over Pydantic AI's `FunctionModel`: the scripted function
    stands in for the provider, and the request, the tool block and the reply
    still travel the adapter's own translation."""

    def __init__(self, reply: FunctionDef) -> None:
        self._model = FunctionModel(reply)

    async def run(self, assembled: AssembledTurn, binding: Binding) -> Completion:
        response = await model_request(
            self._model,
            [
                ModelRequest(
                    parts=[
                        UserPromptPart(content=part.body) for part in assembled.envelope
                    ],
                    instructions=instructions(assembled.prefix),
                )
            ],
            model_request_parameters=ModelRequestParameters(
                function_tools=tool_definitions(assembled.prefix)
            ),
        )
        return completion(response)
