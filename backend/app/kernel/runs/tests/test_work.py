"""The work loop against a real Postgres: one step, a crash, a cancel, an expiry.

The four walking-skeleton claims this wave owes: the dispatching process is
`work`; a worker that dies mid-step costs no duplicate action; a cancel is felt at
the next step boundary and not inside one; and an approval nobody answers hands
the step back with a denial rather than parking the run for good. The clock is
injected everywhere, so a lease and a 72-hour expiry are assertions and not waits.
The prompt's two message slots are here too, because the seam that keeps them
apart — D4's watermark and D5/D6's drain — is the worker's.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from uuid import UUID, uuid4

import pytest
from pydantic_ai.messages import (
    ModelMessage,
    ModelRequest,
    ModelResponse,
    TextPart,
    ToolCallPart,
    UserPromptPart,
)
from pydantic_ai.models.function import AgentInfo, FunctionDef
from sqlalchemy import delete, func, select, text, update

from app.kernel.declare.models import Action, Event
from app.kernel.declare.registry import CallContext, Registry
from app.kernel.declare.service import Call as ToolCall, Committed, dispatch
from app.kernel.identity.models import Approval, Grant
from app.kernel.runs.models import Checkpoint, MailboxMessage, StepQueue
from app.kernel.runs.service import cancel, create, events, send
from app.kernel.runs.tick import EXPIRED, Pass, tick_once
from app.kernel.runs.work import LEASE, PLANNED, Claimed, claim, step, work_once
from app.kernel.store.models import AgentDefinition, Run
from app.kernel.store.service import session
from tests.kit import FakeClock, FakeModelRunner, Scope, two_principals
from tests.kit_notes import grant, note_table, notes_registry

pytestmark = pytest.mark.anyio

WRITE = "note.write_note"
REMOVE = "note.remove_note"
NOTE = "We land on the higher price."
STEER = "Write the note about where we landed on pricing."
AGAIN = "And who else needs to know?"
REPLY = "The note is written."
_NOTE_BODY = text("SELECT body FROM mod_test.note WHERE id = :id")


@dataclass(frozen=True, slots=True)
class Setup:
    """One org of its own, so a leftover queue row of another module's is
    unreachable and the claim cannot pick it up."""

    scope: Scope
    registry: Registry
    definition_id: UUID


@pytest.fixture(scope="module")
async def setup(migrated_url: str) -> Setup:
    await note_table(migrated_url)
    scope = (await two_principals(migrated_url))[0]
    registry = notes_registry()
    async with session(*scope) as scoped:
        await registry.publish(scoped)
        await grant(scoped, scope[2], WRITE, "may_use")
        await grant(scoped, scope[2], REMOVE, "asks_first")
        definition_id = (await scoped.scalars(select(AgentDefinition.id))).one()
        await scoped.commit()
    return Setup(scope, registry, definition_id)


@pytest.fixture(autouse=True)
async def one_run_at_a_time(setup: Setup) -> None:
    """Each test claims its own run: the queue starts empty inside this org."""
    async with session(*setup.scope) as scoped:
        await scoped.execute(delete(StepQueue))
        await scoped.commit()


def _proposes(operation_name: str, note_id: UUID) -> FunctionDef:
    """A model that reads the steer and asks for one operation, by a stable id."""

    def reply(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        return ModelResponse(
            parts=[
                TextPart("Writing that down."),
                ToolCallPart(
                    operation_name,
                    {"note_id": str(note_id), "body": NOTE},
                    tool_call_id="call-1",
                ),
            ]
        )

    return reply


def _answers(seen: list[str]) -> FunctionDef:
    """A model that proposes nothing, which is how a run reaches `done`, and
    keeps the envelope slices it was handed so a test can read them."""

    def reply(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        request = messages[0]
        assert isinstance(request, ModelRequest)
        seen.extend(
            str(part.content)
            for part in request.parts
            if isinstance(part, UserPromptPart)
        )
        return ModelResponse(parts=[TextPart(REPLY)])

    return reply


async def _run(setup: Setup) -> UUID:
    """A run with one steer waiting in its mailbox."""
    async with session(*setup.scope) as scoped:
        definition = await scoped.get_one(AgentDefinition, setup.definition_id)
        run = await create(scoped, definition, None, stage="DEV")
        await send(scoped, run.id, STEER)
        await scoped.commit()
        return run.id


async def _work(setup: Setup, reply: FunctionDef, clock: FakeClock) -> str | None:
    return await work_once(
        setup.scope,
        worker_id="worker-a",
        runner=FakeModelRunner(reply),
        registry=setup.registry,
        clock=clock.now,
    )


async def _actions(setup: Setup, run_id: UUID) -> int:
    """Every action this run's ledger carries, however many workers wrote them."""
    async with session(*setup.scope) as scoped:
        return (
            await scoped.scalar(
                select(func.count())
                .select_from(Action)
                .join(Event, Event.id == Action.event_id)
                .where(Event.run_id == run_id)
            )
        ) or 0


async def test_action_runs_in_worker(setup: Setup) -> None:
    """Walking skeleton: the process that dispatches an operation is `work`."""
    run_id, note_id = await _run(setup), uuid4()

    state = await _work(setup, _proposes(WRITE, note_id), FakeClock())

    assert state == "queued"
    assert await _actions(setup, run_id) == 1
    async with session(*setup.scope) as scoped:
        assert await scoped.scalar(_NOTE_BODY, {"id": note_id}) == NOTE
        checkpoint = await scoped.scalar(
            select(Checkpoint).where(Checkpoint.run_id == run_id)
        )
        assert checkpoint is not None
        assert checkpoint.step_no == 1
        # The drained steer is watermarked, so step 2 does not read it again.
        assert checkpoint.state["mailbox_seq"] == 1
        # The plan is journaled under the same id the reservation key was built on.
        planned = [
            one.payload
            for one in await events(scoped, run_id)
            if one.payload.get("event") == PLANNED
        ]
        assert planned[0]["calls"] == [
            {
                "name": WRITE,
                "args": {"note_id": str(note_id), "body": NOTE},
                "tool_call_id": "call-1",
            }
        ]
        # A proposed call means there is more to do: the next step is queued.
        assert await scoped.scalar(
            select(StepQueue.step_no).where(StepQueue.run_id == run_id)
        ) == 2

    # And a turn that proposes nothing ends the run.
    assert await _work(setup, _answers([]), FakeClock()) == "done"


async def test_crash_replay_no_duplicate(setup: Setup) -> None:
    """Worker A dies after its ledger commit; worker B works the same step."""
    run_id, note_id = await _run(setup), uuid4()
    clock = FakeClock()

    async with session(*setup.scope) as scoped:
        claimed = await claim(scoped, worker_id="worker-a", now=clock.now())
        await scoped.commit()
    assert claimed == Claimed(run_id, 1)

    # A's step got as far as committing its one call, and then A was gone.
    async with session(*setup.scope) as scoped:
        outcome = await dispatch(
            CallContext(
                session=scoped,
                principal_id=setup.scope[2],
                run_id=run_id,
                step_no=1,
                registry=setup.registry,
                clock=clock.now,
            ),
            ToolCall(WRITE, {"note_id": str(note_id), "body": NOTE}, "call-1", 0),
        )
        await scoped.commit()
    assert isinstance(outcome, Committed)

    # `tick` clears the dead lease, and B claims the step A never finished.
    clock.advance(LEASE.total_seconds() + 1)
    assert await tick_once(setup.scope, clock=clock.now) == Pass(reaped=1, expired=0)
    assert await _work(setup, _proposes(WRITE, note_id), clock) == "queued"

    assert await _actions(setup, run_id) == 1
    async with session(*setup.scope) as scoped:
        replayed = await scoped.scalar(
            select(Checkpoint.state).where(Checkpoint.run_id == run_id)
        )
        assert replayed is not None
        results = replayed["results"]
        assert isinstance(results, list)
        assert results[0]["outcome"] == "replayed"


async def test_cancel_stops_at_step_boundary(setup: Setup) -> None:
    """A cancelled run is never claimed again, and its approvals stop standing."""
    run_id = await _run(setup)
    async with session(*setup.scope) as scoped:
        assert await cancel(scoped, run_id) is True
        await scoped.commit()

    assert await _work(setup, _proposes(WRITE, uuid4()), FakeClock()) is None

    async with session(*setup.scope) as scoped:
        run = await scoped.get_one(Run, run_id)
        assert run.state == "cancelled"
        answerable = await scoped.scalar(
            select(func.count())
            .select_from(Approval)
            .where(Approval.run_id == run_id, Approval.state.in_(("requested", "open")))
        )
        assert answerable == 0


async def test_cancel_mid_step_is_not_resurrected(setup: Setup) -> None:
    """Cancel lands between a claim and its step: the step's committed call
    stands in the ledger, and the run stays cancelled — no new state, no
    checkpoint, no next queue row."""
    run_id, note_id = await _run(setup), uuid4()
    clock = FakeClock()
    async with session(*setup.scope) as scoped:
        claimed = await claim(scoped, worker_id="worker-a", now=clock.now())
        await scoped.commit()
    assert claimed is not None and claimed == Claimed(run_id, 1)

    async with session(*setup.scope) as scoped:
        assert await cancel(scoped, run_id) is True
        await scoped.commit()

    async with session(*setup.scope) as scoped:
        settled = await step(
            scoped,
            claimed,
            runner=FakeModelRunner(_proposes(WRITE, note_id)),
            registry=setup.registry,
            clock=clock.now,
        )
        await scoped.commit()
    assert settled == "cancelled"

    async with session(*setup.scope) as scoped:
        run = await scoped.get_one(Run, run_id)
        assert run.state == "cancelled"
        for leftover in (StepQueue, Checkpoint):
            assert await scoped.scalar(
                select(func.count())
                .select_from(leftover)
                .where(leftover.run_id == run_id)
            ) == 0


async def test_grant_widened_after_create_is_capped_by_the_ceiling(
    setup: Setup,
) -> None:
    """ADR-0015: the ceiling is fixed at create. REMOVE was asks_first then, so
    a later may_use grant still parks the call instead of committing it."""
    run_id = await _run(setup)
    note_id = uuid4()

    def _remove_level(level: str):
        return (
            update(Grant)
            .where(
                Grant.principal_id == setup.scope[2],
                Grant.operation_name == REMOVE,
            )
            .values(level=level)
        )

    async with session(*setup.scope) as scoped:
        await scoped.execute(_remove_level("may_use"))
        await scoped.commit()
    try:
        state = await _work(setup, _proposes(REMOVE, note_id), FakeClock())
        assert state == "waiting_approval"
    finally:
        async with session(*setup.scope) as scoped:
            # The park left a requested approval; cancel expires it so the
            # expiry test's Pass count stays its own.
            assert await cancel(scoped, run_id) is True
            await scoped.execute(_remove_level("asks_first"))
            await scoped.commit()


async def test_expired_approval_requeues_step(setup: Setup) -> None:
    """Nobody answers in 72 hours: the step comes back and is refused, not stuck."""
    run_id, note_id = await _run(setup), uuid4()
    clock = FakeClock()
    reply = _proposes(REMOVE, note_id)

    assert await _work(setup, reply, clock) == "waiting_approval"
    async with session(*setup.scope) as scoped:
        # Parked, so nothing was checkpointed: the step must drain and plan again.
        assert await scoped.scalar(
            select(func.count())
            .select_from(Checkpoint)
            .where(Checkpoint.run_id == run_id)
        ) == 0

    clock.advance(timedelta(hours=72).total_seconds() + 1)
    assert await tick_once(setup.scope, clock=clock.now) == Pass(reaped=0, expired=1)
    async with session(*setup.scope) as scoped:
        run = await scoped.get_one(Run, run_id)
        assert run.state == "queued"
        approval = await scoped.scalar(
            select(Approval).where(Approval.run_id == run_id)
        )
        assert approval is not None
        assert (approval.state, approval.reason) == (EXPIRED, EXPIRED)
        assert await scoped.scalar(
            select(StepQueue.step_no).where(StepQueue.run_id == run_id)
        ) == 1

    assert await _work(setup, reply, clock) == "queued"
    async with session(*setup.scope) as scoped:
        denials = [
            one.payload
            for one in await events(scoped, run_id)
            if one.kind == "denial"
        ]
        assert denials[-1]["reason"] == "approval_unavailable"
        assert denials[-1]["state"] == EXPIRED
        assert denials[-1]["approval_reason"] == EXPIRED


async def test_transcript_holds_the_earlier_turns_only(setup: Setup) -> None:
    """A message to a finished run wakes it, and the next prompt carries the
    conversation so far in D4 with this step's own message in D6 — no message in
    both, because the drain's watermark is exactly the transcript's ceiling."""
    run_id = await _run(setup)
    first: list[str] = []
    assert await _work(setup, _answers(first), FakeClock()) == "done"
    # The first step has no conversation behind it, so it contributes no D4.
    assert first == [f"[steer] {STEER}"]

    async with session(*setup.scope) as scoped:
        assert isinstance(await send(scoped, run_id, AGAIN), MailboxMessage)
        await scoped.commit()
    async with session(*setup.scope) as scoped:
        run = await scoped.get_one(Run, run_id)
        assert run.state == "queued"
        assert await scoped.scalar(
            select(StepQueue.step_no).where(StepQueue.run_id == run_id)
        ) == 2

    seen: list[str] = []
    assert await _work(setup, _answers(seen), FakeClock()) == "done"
    transcript, intake = seen
    assert transcript == f"[person] {STEER}\n\n[agent] {REPLY}"
    assert intake == f"[steer] {AGAIN}"
