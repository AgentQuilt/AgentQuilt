"""Fixture kit shared by the kernel modules' own test folders."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import httpx
from pydantic_ai import models
from pydantic_ai.direct import model_request
from pydantic_ai.messages import ModelRequest, UserPromptPart
from pydantic_ai.models import ModelRequestParameters
from pydantic_ai.models.function import FunctionDef, FunctionModel
from sqlalchemy import select, text
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
from app.kernel.declare.models import Action, Event, OperationVersion
from app.kernel.store.models import AgentDefinition, Run, Skill, SkillVersion
from app.kernel.store.seed import seed
from app.kernel.store.service import Scope, session

# No test in this suite may reach a provider; the fake below goes through
# `FunctionModel`, which this flag does not gate.
models.ALLOW_MODEL_REQUESTS = False

START = datetime(2026, 1, 1, tzinfo=UTC)
# The body of the skill version `dev_skill_version` writes: what a test that
# follows the version into the model's prompt looks for.
SKILL_BODY = "Answer from the notes, and say when the notes are silent."


async def two_principals(url: str) -> tuple[Scope, Scope]:
    """Seed two orgs and hand back their prod planes, one system scope each."""
    first, second = await seed()
    return (
        (first.org_id, first.prod_environment_id, first.system_principal_id),
        (second.org_id, second.prod_environment_id, second.system_principal_id),
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


def bearer_client(
    serve_url: str, token: str, *, timeout: float = 5.0
) -> httpx.AsyncClient:
    """The HTTP interface as one org's person sees it: every request carries the
    token `seed` printed, and nothing else authenticates."""
    return httpx.AsyncClient(
        base_url=serve_url,
        headers={"Authorization": f"Bearer {token}"},
        timeout=timeout,
    )


async def sse_frames(
    client: httpx.AsyncClient, url: str, *, cursor: int = 0, count: int = 1
) -> list[dict[str, str]]:
    """Read `count` frames off a stream and hang up, which is what a reload does.

    Comment lines are skipped, so a keep-alive is never read as an event, and a
    stream with nothing to say runs into the client's read timeout: that is how a
    test asserts silence.
    """
    headers = {"Last-Event-ID": str(cursor)} if cursor else {}
    frames: list[dict[str, str]] = []
    fields: dict[str, str] = {}
    async with client.stream("GET", url, headers=headers) as response:
        assert response.status_code == 200
        async for line in response.aiter_lines():
            if line.startswith(":"):
                continue
            if line:
                name, _, value = line.partition(": ")
                fields[name] = value
            elif fields:
                frames.append(fields)
                if len(frames) == count:
                    return frames
                fields = {}
    raise AssertionError(f"{url} closed after {len(frames)} frames, wanted {count}")


async def a_run(scope: Scope) -> UUID:
    """One committed run, on the scope's own plane.

    Journal events and approvals carry scope-carrying keys onto `core.run` as of
    the environment rail, so a test that hangs either off a run needs a real one;
    a fabricated id is no longer a stand-in.
    """
    async with session(*scope) as scoped:
        definition = await scoped.scalar(select(AgentDefinition.id).limit(1))
        assert definition is not None
        run = Run(
            id=uuid4(),
            org_id=scope[0],
            agent_definition_id=definition,
            stage="DEV",
            state="running",
            budget_cap_tokens=1000,
            prefix_key="pk",
            capability_ceiling={},
            prefix_profile="personal",
        )
        scoped.add(run)
        await scoped.commit()
        return run.id


async def an_action(scope: Scope) -> UUID:
    """One committed, irreversible action on the scope's plane.

    Written as the pair rather than through dispatch, because the callers want
    an action to address a route at, not a call to make; no compensator, so undo
    refuses it the way it refuses any irreversible operation.
    """
    async with session(*scope) as scoped:
        # The ledger is append-only: its two tables take inserts from one role.
        await scoped.execute(text("SET LOCAL ROLE agentquilt_ledger_writer"))
        version_id = await scoped.scalar(select(OperationVersion.id).limit(1))
        assert version_id is not None
        action_id = uuid4()
        event = Event(
            org_id=scope[0],
            kind="operation_commit",
            aggregate_kind="thing",
            aggregate_id=uuid4(),
            aggregate_version=1,
            principal_id=scope[2],
            payload={},
            action_id=action_id,
        )
        scoped.add(event)
        # The event first: the action points back at it, and the deferred pair
        # settles at COMMIT.
        await scoped.flush()
        scoped.add(
            Action(
                id=action_id,
                org_id=scope[0],
                event_id=event.id,
                operation_version_id=version_id,
                idempotency_key=str(uuid4()),
                decision_trace={},
            )
        )
        await scoped.commit()
        return action_id


async def dev_skill_version(session: AsyncSession, org_id: UUID) -> str:
    """One skill and one DEV version of it, ready to be activated."""
    skill_id, version_id = uuid4(), str(uuid4())
    session.add(Skill(id=skill_id, org_id=org_id, name=f"skill {skill_id}"))
    await session.flush()
    session.add(
        SkillVersion(
            id=version_id,
            org_id=org_id,
            skill_id=skill_id,
            tier="executor",
            execution_mode="inline",
            operations={},
            stage="DEV",
            body=SKILL_BODY,
        )
    )
    await session.flush()
    return version_id
