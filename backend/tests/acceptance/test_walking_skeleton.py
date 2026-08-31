"""The twelve clauses of the first slice, proven at the outermost seam.

Each clause of the walking-skeleton flow is one test, and each test drives the
product the way the deployment does: everything a person does goes through HTTP
with the token `seed` printed, and the `work` role runs in this process as
`work_once` with the model scripted through `FunctionModel`. What a module proves
at its own seam is not restated here — it is proven again through the interface.

Two things have no route in Phase 1 and are named where they are used: a run is
cancelled through `runs.cancel`, and a run binds its skill version through
`runs.create`, the call `POST /threads` makes with no version of its own. A parked
approval has no route either, but it has a journal event, so its id is read off
the run's stream the way a person reads it.
"""

from __future__ import annotations

import json
import os
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import cast
from uuid import UUID, uuid4

import httpx
import pytest
from pydantic_ai import models
from pydantic_ai.messages import (
    ModelMessage,
    ModelRequest,
    ModelResponse,
    TextPart,
    ToolCallPart,
    UserPromptPart,
)
from pydantic_ai.models.function import AgentInfo, FunctionDef
from sqlalchemy import delete, select, update

from app.kernel.declare.models import Action, Event, Json
from app.kernel.declare.registry import registry
from app.kernel.identity.models import Approval
from app.kernel.model.adapter import PydanticAIModelRunner
from app.kernel.model.models import UsageRecord
from app.kernel.runs.models import Checkpoint, StepQueue
from app.kernel.runs.service import cancel, create
from app.kernel.runs.work import PARKED, PLANNED, work_once
from app.kernel.store.models import AgentDefinition, Principal, Run, SkillVersion
from app.kernel.store.seed import SeededOrg, seed
from app.kernel.store.service import session
from app.modules.governance.service import NAME as DECIDE, UNDO
from app.modules.skills.service import ACTIVATE, activate, directory
from tests.kit import (
    SKILL_BODY,
    FakeModelRunner,
    Scope,
    bearer_client,
    dev_skill_version,
    sse_frames,
)
from tests.kit_notes import grant

pytestmark = pytest.mark.anyio

WORKER = "acceptance"
SAYS = "Promoting that version."
STEER = "Promote the new skill version."
CALL = "call-1"
KEY_VAR = "OPENROUTER_API_KEY"
# Long enough that a stream with something to say has said it; short enough that
# the silence a foreign org gets is an assertion and not a wait.
SILENT_SECONDS = 3.0


@dataclass(frozen=True, slots=True)
class Deployment:
    """Two orgs as `seed` leaves them, and the scope the `work` role runs in."""

    a: SeededOrg
    b: SeededOrg
    scope: Scope


@pytest.fixture(scope="module")
async def space(migrated_url: str) -> Deployment:
    """The deployment: two seeded orgs, the operations published, and org A's
    person granted the two governance operations a person calls by hand."""
    a, b = await seed()
    async with session(a.org_id, a.system_principal_id) as scoped:
        await registry.publish(scoped)
        person = (
            await scoped.scalars(select(Principal.id).where(Principal.class_ == "user"))
        ).one()
        for name in (DECIDE, UNDO):
            await grant(scoped, person, name, "may_use")
        await scoped.commit()
    return Deployment(a, b, (a.org_id, a.system_principal_id))


@pytest.fixture(autouse=True)
async def one_run_at_a_time(space: Deployment) -> None:
    """Each test works its own run: the queue starts empty inside org A."""
    async with session(*space.scope) as scoped:
        await scoped.execute(delete(StepQueue))
        await scoped.commit()


@pytest.fixture
async def person(space: Deployment, serve_url: str) -> AsyncIterator[httpx.AsyncClient]:
    """Org A's user at the HTTP interface."""
    async with bearer_client(serve_url, space.a.token) as client:
        yield client


@pytest.fixture
async def stranger(
    space: Deployment, serve_url: str
) -> AsyncIterator[httpx.AsyncClient]:
    """Org B's user, who has a token and no business with org A's run."""
    async with bearer_client(
        serve_url, space.b.token, timeout=SILENT_SECONDS
    ) as client:
        yield client


def _proposes(name: str, args: dict[str, str]) -> FunctionDef:
    """A model that says one line and asks for one operation, by a stable id."""

    def reply(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        return ModelResponse(
            parts=[TextPart(SAYS), ToolCallPart(name, args, tool_call_id=CALL)]
        )

    return reply


def _never() -> FunctionDef:
    """A model that must not be reached: the run was stopped before the call."""

    def reply(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        raise AssertionError("the model was reached past a run that had stopped")

    return reply


def _mapping(value: object) -> Json:
    """A JSON object, narrowed where a test reads inside one."""
    assert isinstance(value, dict)
    return cast("Json", value)


def _payload(frame: dict[str, str]) -> Json:
    """One SSE frame's ledger payload; the frame's `event` is the event kind."""
    return _mapping(_mapping(json.loads(frame["data"]))["payload"])


def _records(seen: list[str]) -> FunctionDef:
    """A model that proposes nothing and keeps the prompt it was handed."""

    def reply(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        request = messages[0]
        assert isinstance(request, ModelRequest)
        seen.append(str(request.instructions))
        seen.extend(
            str(part.content)
            for part in request.parts
            if isinstance(part, UserPromptPart)
        )
        return ModelResponse(parts=[TextPart(SAYS)])

    return reply


async def _work(space: Deployment, reply: FunctionDef) -> str | None:
    """One turn of the `work` role, in this process, against the scripted model."""
    return await work_once(
        space.scope,
        worker_id=WORKER,
        runner=FakeModelRunner(reply),
        registry=registry,
    )


async def _thread(person: httpx.AsyncClient) -> UUID:
    """A person opens a thread and steers it once: the run the worker will claim."""
    opened = await person.post("/threads")
    assert opened.status_code == 201
    run_id = UUID(opened.json()["run_id"])
    steered = await person.post(f"/runs/{run_id}/messages", json={"text": STEER})
    assert steered.status_code == 202
    return run_id


async def _version(space: Deployment) -> str:
    """A DEV skill version of org A's, waiting to be promoted."""
    async with session(*space.scope) as scoped:
        version_id = await dev_skill_version(scoped, space.a.org_id)
        await scoped.commit()
    return version_id


async def _park(space: Deployment, run_id: UUID, args: dict[str, str]) -> Approval:
    """Work one step that asks first, and read the approval it parked on.

    Phase 1 has no route that lists a parked approval, so the id a person answers
    with comes off the run's stream; clause 5 is where that reading is asserted.
    """
    assert await _work(space, _proposes(ACTIVATE, args)) == "waiting_approval"
    async with session(*space.scope) as scoped:
        return (
            await scoped.scalars(
                select(Approval).where(
                    Approval.run_id == run_id, Approval.state == "requested"
                )
            )
        ).one()


async def _approve(person: httpx.AsyncClient, approval_id: UUID) -> None:
    decided = await person.post(
        f"/approvals/{approval_id}/decide", json={"decision": "approve"}
    )
    assert decided.status_code == 200
    assert decided.json()["decided"] is True


async def _actions(space: Deployment, run_id: UUID) -> list[Action]:
    """Every action this run's ledger carries."""
    async with session(*space.scope) as scoped:
        return list(
            await scoped.scalars(
                select(Action)
                .join(Event, Event.id == Action.event_id)
                .where(Event.run_id == run_id)
            )
        )


async def _stage(space: Deployment, version_id: str) -> str:
    async with session(*space.scope) as scoped:
        return (await scoped.get_one(SkillVersion, version_id)).stage


async def _cap(space: Deployment, tokens: int) -> None:
    """The org's agent definition budget: what a new run's cap is copied from."""
    async with session(*space.scope) as scoped:
        await scoped.execute(update(AgentDefinition).values(budget_cap_tokens=tokens))
        await scoped.commit()


async def _committed(
    space: Deployment, person: httpx.AsyncClient, run_id: UUID
) -> tuple[str, Action]:
    """The whole approved path: park, answer through HTTP, work the same step.

    The second turn plans the same call with the same tool call id, which is what
    binds it to the approval the person just opened.
    """
    version_id = await _version(space)
    args = {"skill_version_id": version_id, "stage": "PROD"}
    await _approve(person, (await _park(space, run_id, args)).id)
    assert await _work(space, _proposes(ACTIVATE, args)) == "queued"
    (action,) = await _actions(space, run_id)
    return version_id, action


async def test_user_creates_run(space: Deployment, person: httpx.AsyncClient) -> None:
    """Clause 1: a person's thread is a run of their org, with a stored ceiling."""
    run_id = await _thread(person)
    async with session(*space.scope) as scoped:
        run = await scoped.get_one(Run, run_id)
        queued = await scoped.scalar(
            select(StepQueue.step_no).where(StepQueue.run_id == run_id)
        )
    assert (run.org_id, run.state) == (space.a.org_id, "queued")
    # ADR-0015: the ceiling is the creating person's grants, fixed at create.
    assert _mapping(run.capability_ceiling["operations"])[ACTIVATE] == "asks_first"
    assert queued == 1


async def test_run_binds_one_skill_version(space: Deployment) -> None:
    """Clause 2: one PROD version is bound, and its body is what the model reads.

    `POST /threads` starts a thread with no skill version, so the binding is made
    through `runs.create`, the same call that route makes.
    """
    version_id = await _version(space)
    async with session(*space.scope) as scoped:
        assert await activate(scoped, version_id, "PROD") == "DEV"
        assert version_id in [one.version_id for one in await directory(scoped)]
        definition = (await scoped.scalars(select(AgentDefinition))).one()
        version = await scoped.get_one(SkillVersion, version_id)
        run = await create(scoped, definition, version)
        await scoped.commit()

    seen: list[str] = []
    assert await _work(space, _records(seen)) == "done"
    assert any(SKILL_BODY in one for one in seen)
    async with session(*space.scope) as scoped:
        assert (await scoped.get_one(Run, run.id)).skill_version_id == version_id


async def test_fake_model_proposes_action(
    space: Deployment, person: httpx.AsyncClient
) -> None:
    """Clause 3: the plan reaches the ledger before any of it is dispatched."""
    run_id = await _thread(person)
    args = {"skill_version_id": await _version(space), "stage": "PROD"}
    await _park(space, run_id, args)

    created, planned = await sse_frames(person, f"/runs/{run_id}/events", count=2)
    assert created["event"] == "run_journal"
    payload = _payload(planned)
    assert payload["event"] == PLANNED
    assert payload["text"] == SAYS
    assert payload["calls"] == [
        {"name": ACTIVATE, "args": args, "tool_call_id": CALL}
    ]


async def test_grant_checked_at_call_time(
    space: Deployment, person: httpx.AsyncClient
) -> None:
    """Clause 4: the acting principal's grants decide, and a refusal is journaled.

    The run's ceiling carries `governance.decide_approval`, because the person who
    opened the thread is granted it; the worker is not, and the intersection is
    what dispatch checks.
    """
    run_id = await _thread(person)
    proposed = {"approval_id": str(uuid4()), "decision": "approve"}
    assert await _work(space, _proposes(DECIDE, proposed)) == "queued"

    frames = await sse_frames(person, f"/runs/{run_id}/events", count=3)
    assert frames[-1]["event"] == "denial"
    denial = _payload(frames[-1])
    assert (denial["reason"], denial["operation_name"]) == ("no_grant", DECIDE)
    assert await _actions(space, run_id) == []


async def test_asks_first_opens_approval(
    space: Deployment, person: httpx.AsyncClient
) -> None:
    """Clause 5: an `asks_first` call opens an approval and parks its step."""
    run_id = await _thread(person)
    version_id = await _version(space)
    approval = await _park(
        space, run_id, {"skill_version_id": version_id, "stage": "PROD"}
    )

    assert (approval.run_id, approval.step_no, approval.tool_call_id) == (
        run_id,
        1,
        CALL,
    )
    # The id a person answers with is the one the stream carries: the third
    # frame is the park, after the run's creation and the step's plan.
    parked = _payload((await sse_frames(person, f"/runs/{run_id}/events", count=3))[-1])
    assert parked["event"] == PARKED
    assert parked["approval_id"] == str(approval.id)
    assert parked["operation_name"] == ACTIVATE
    async with session(*space.scope) as scoped:
        run = await scoped.get_one(Run, run_id)
        # No checkpoint and no queue row: the same step is worked again when the
        # approval is answered, and it drains and plans from the same place.
        left = await scoped.scalars(
            select(Checkpoint.id).where(Checkpoint.run_id == run_id)
        )
        queued = await scoped.scalar(
            select(StepQueue.step_no).where(StepQueue.run_id == run_id)
        )
    assert run.state == "waiting_approval"
    assert left.all() == []
    assert queued is None
    assert await _stage(space, version_id) == "DEV"


async def test_approval_binds_to_digest(
    space: Deployment, person: httpx.AsyncClient
) -> None:
    """Clause 6: the answer is bound to the exact arguments it was asked about.

    The second turn proposes the same operation at the same continuation with one
    argument changed. The open approval is not spendable against it, so the call
    parks again and the approval the person answered is still unspent.
    """
    run_id = await _thread(person)
    version_id = await _version(space)
    answered = await _park(
        space, run_id, {"skill_version_id": version_id, "stage": "PROD"}
    )
    await _approve(person, answered.id)

    changed = {"skill_version_id": version_id, "stage": "DEV"}
    assert await _work(space, _proposes(ACTIVATE, changed)) == "waiting_approval"
    async with session(*space.scope) as scoped:
        spent = await scoped.get_one(Approval, answered.id)
        asked = (
            await scoped.scalars(
                select(Approval).where(
                    Approval.run_id == run_id, Approval.state == "requested"
                )
            )
        ).one()
    assert (spent.state, spent.consumed_by_action_id) == ("open", None)
    assert asked.args_hash != spent.args_hash
    assert await _stage(space, version_id) == "DEV"


async def test_action_runs_in_worker(
    space: Deployment, person: httpx.AsyncClient
) -> None:
    """Clause 7: the process that dispatches the approved call is `work`."""
    run_id = await _thread(person)
    version_id, action = await _committed(space, person, run_id)

    assert action.operation_version_id == registry.version_id(registry.get(ACTIVATE))
    assert await _stage(space, version_id) == "PROD"
    async with session(*space.scope) as scoped:
        approval = await scoped.get_one(Approval, action.approval_id)
        event = await scoped.get_one(Event, action.event_id)
    # The approval was spent by this action, in this run's step, by the worker.
    assert (approval.state, approval.consumed_by_action_id) == ("consumed", action.id)
    assert (event.run_id, event.step_no) == (run_id, 1)


async def test_events_stream_and_replay(
    space: Deployment, person: httpx.AsyncClient
) -> None:
    """Clause 8: the ledger streams, and a reconnect resumes at the cursor."""
    run_id = await _thread(person)
    stream = f"/runs/{run_id}/events"
    (created,) = await sse_frames(person, stream)
    assert _payload(created)["event"] == "run.created"

    # The plan lands while nobody is reading, so only the reconnect delivers it.
    args = {"skill_version_id": await _version(space), "stage": "PROD"}
    await _park(space, run_id, args)

    (resumed,) = await sse_frames(person, stream, cursor=int(created["id"]))
    assert int(resumed["id"]) > int(created["id"])
    assert _payload(resumed)["event"] == PLANNED


async def test_action_written_and_undoable(
    space: Deployment, person: httpx.AsyncClient
) -> None:
    """Clause 9: the action records what reversing it needs, and undo reverses it.

    Undo starts a run rather than compensating in place, so the reversal is an
    ordinary call: the worker proposes the compensator the action recorded, the
    person answers for it, and only then is the version back where it was.
    """
    run_id = await _thread(person)
    version_id, action = await _committed(space, person, run_id)
    assert action.compensator_ref == ACTIVATE
    assert action.compensator_args == {
        "skill_version_id": version_id,
        "stage": "DEV",
    }

    undone = await person.post(f"/actions/{action.id}/undo")
    assert undone.status_code == 200
    assert undone.json()["compensator"] == ACTIVATE
    undo_run = UUID(undone.json()["undo_run_id"])

    compensating = {"skill_version_id": version_id, "stage": "DEV"}
    await _approve(person, (await _park(space, undo_run, compensating)).id)
    assert await _work(space, _proposes(ACTIVATE, compensating)) == "queued"
    assert await _stage(space, version_id) == "DEV"
    assert len(await _actions(space, undo_run)) == 1


async def test_retry_returns_stored_action(
    space: Deployment, person: httpx.AsyncClient
) -> None:
    """Clause 10: the same call worked twice commits once.

    The queue is put back the way `tick` leaves it when a worker dies after its
    ledger commit and before it settles: this step free again, nothing queued
    after it, and the next worker planning the same call under the same tool call
    id, whose reservation the dead worker already spent.
    """
    run_id = await _thread(person)
    version_id, action = await _committed(space, person, run_id)
    async with session(*space.scope) as scoped:
        await scoped.execute(delete(StepQueue).where(StepQueue.run_id == run_id))
        scoped.add(
            StepQueue(
                org_id=space.a.org_id, run_id=run_id, step_no=1, queue_tag="main"
            )
        )
        await scoped.commit()

    args = {"skill_version_id": version_id, "stage": "PROD"}
    assert await _work(space, _proposes(ACTIVATE, args)) == "queued"
    assert [one.id for one in await _actions(space, run_id)] == [action.id]
    async with session(*space.scope) as scoped:
        checkpoints = (
            await scoped.scalars(
                select(Checkpoint.state).where(Checkpoint.run_id == run_id)
            )
        ).all()
    replayed = {
        "tool_call_id": CALL,
        "outcome": "replayed",
        "action_id": str(action.id),
    }
    assert [replayed] in [one["results"] for one in checkpoints]


async def test_org_b_cannot_read_or_steer(
    space: Deployment, person: httpx.AsyncClient, stranger: httpx.AsyncClient
) -> None:
    """Clause 11: another org's token neither steers the run nor reads it."""
    run_id = await _thread(person)
    args = {"skill_version_id": await _version(space), "stage": "PROD"}
    await _park(space, run_id, args)

    steered = await stranger.post(f"/runs/{run_id}/messages", json={"text": STEER})
    assert steered.status_code == 404
    # Row-level security hides the run, so the stream has nothing to send and the
    # reader waits until its own timeout rather than reading someone else's ledger.
    with pytest.raises(httpx.ReadTimeout):
        await sse_frames(stranger, f"/runs/{run_id}/events")
    # And the org that owns it reads the same stream without waiting.
    assert len(await sse_frames(person, f"/runs/{run_id}/events", count=2)) == 2


async def test_cancel_and_budget(
    space: Deployment, person: httpx.AsyncClient
) -> None:
    """Clause 12: a cancelled run is never worked again, and a run over its cap
    is refused before the provider is called, not after.

    Cancellation has no route in Phase 1, so it is `runs.cancel`; the cap is the
    agent definition's, which is what `POST /threads` copies onto the run.
    """
    run_id = await _thread(person)
    async with session(*space.scope) as scoped:
        assert await cancel(scoped, run_id) is True
        await scoped.commit()
    assert await _work(space, _never()) is None
    async with session(*space.scope) as scoped:
        assert (await scoped.get_one(Run, run_id)).state == "cancelled"

    await _cap(space, 1)
    try:
        broke = await _thread(person)
        assert await _work(space, _never()) == "failed"
    finally:
        await _cap(space, 200_000)

    async with session(*space.scope) as scoped:
        run = await scoped.get_one(Run, broke)
    assert run.failure_reason == "budget_exceeded"
    frames = await sse_frames(person, f"/runs/{broke}/events", count=2)
    assert frames[-1]["event"] == "denial"
    assert _payload(frames[-1])["reason"] == "budget_exceeded"



@pytest.mark.skipif(
    os.getenv(KEY_VAR) is None, reason=f"{KEY_VAR} is not set in this environment"
)
async def test_real_provider_smoke(
    space: Deployment, person: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The same first turn against the real provider. Non-blocking; costs money.

    Nothing is asserted about what the model says: the point is that the seeded
    tier binding reaches a provider through the port and the turn is paid for.
    """
    monkeypatch.setattr(models, "ALLOW_MODEL_REQUESTS", True)
    run_id = await _thread(person)
    state = await work_once(
        space.scope,
        worker_id=WORKER,
        runner=PydanticAIModelRunner(),
        registry=registry,
    )
    assert state in ("queued", "done", "waiting_approval")
    async with session(*space.scope) as scoped:
        spent = (
            await scoped.scalars(
                select(UsageRecord).where(UsageRecord.run_id == run_id)
            )
        ).all()
    assert [one for one in spent if one.input_tokens > 0]
