"""The whole approval loop: a call parks, a person answers, the replay commits.

Every step goes through `dispatch` against a real Postgres, because the approval is
spent by one UPDATE whose predicate is the session's org and the row lock is what
makes two deciders safe. The clock is injected, so expiry is a test and not a wait.
"""

from __future__ import annotations

import hashlib
from datetime import timedelta
from uuid import UUID, uuid4

import pytest
from sqlalchemy import Select, func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.kernel.declare.models import IdempotencyKey
from app.kernel.declare.registry import CallContext, Registry
from app.kernel.declare.registry import registry as process_registry
from app.kernel.declare.service import (
    Call,
    Committed,
    Denied,
    WaitingApproval,
    dispatch,
)
from app.kernel.identity.models import Approval
from app.kernel.store.service import session
from app.modules.governance.service import NAME as DECIDE
from tests.kit import START, FakeClock, Scope, two_principals
from tests.kit_notes import grant, note_table, notes_registry

pytestmark = pytest.mark.anyio

WRITE = "note.write_note"
_NOTE_BODY = text("SELECT body FROM mod_test.note WHERE id = :id")
_RUN = text(
    "INSERT INTO core.run (id, org_id, agent_definition_id, stage, state,"
    " budget_cap_tokens, prefix_key, capability_ceiling, prefix_profile)"
    " SELECT :run, :org, id, 'DEV', :state, 1000, 'pk', '{}'::jsonb, 'personal'"
    " FROM core.agent_definition LIMIT 1"
)
_RUN_STATE = text("SELECT state FROM core.run WHERE id = :run")
_QUEUED = text(
    "SELECT count(*) FROM core.step_queue WHERE run_id = :run AND step_no = 1"
)


@pytest.fixture(scope="module")
async def scope(migrated_url: str) -> Scope:
    return (await two_principals(migrated_url))[0]


@pytest.fixture(scope="module")
async def notes(migrated_url: str, scope: Scope) -> Registry:
    """The toy table and both registries published: notes ask first, deciding does not.

    The principal is the org's system principal, which is a class ADR-0004 lets
    decide, so one principal parks the call and answers it.
    """
    await note_table(migrated_url)
    registry = notes_registry()
    async with session(*scope) as scoped:
        await registry.publish(scoped)
        await process_registry.publish(scoped)
        await grant(scoped, scope[1], WRITE, "asks_first")
        await grant(scoped, scope[1], DECIDE, "may_use")
        await scoped.commit()
    return registry


def _ctx(
    scoped: AsyncSession,
    scope: Scope,
    registry: Registry,
    run: UUID,
    clock: FakeClock,
) -> CallContext:
    return CallContext(
        session=scoped,
        principal_id=scope[1],
        run_id=run,
        step_no=1,
        registry=registry,
        clock=clock.now,
    )


def _write(note_id: UUID, body: str, tool_call_id: str) -> Call:
    return Call(
        operation_name=WRITE,
        args={"note_id": str(note_id), "body": body},
        tool_call_id=tool_call_id,
        expected_version=0,
    )


def _reservation(run: UUID, tool_call_id: str) -> Select[tuple[int]]:
    """The reservation dispatch holds for one continuation, by its key (ADR-0004)."""
    digest = hashlib.sha256(f"{run}:1:{tool_call_id}".encode()).hexdigest()
    return (
        select(func.count())
        .select_from(IdempotencyKey)
        .where(
            IdempotencyKey.idempotency_key == digest,
            IdempotencyKey.action_id.is_(None),
        )
    )


async def _decide(
    scoped: AsyncSession,
    scope: Scope,
    clock: FakeClock,
    approval_id: UUID,
    decision: str,
) -> Committed:
    """Dispatch the decision as the deciding principal, and insist it committed."""
    args: dict[str, object] = {"approval_id": str(approval_id), "decision": decision}
    if decision == "reject":
        args["reason"] = "not this note"
    outcome = await dispatch(
        _ctx(scoped, scope, process_registry, uuid4(), clock),
        Call(
            operation_name=DECIDE,
            args=args,
            tool_call_id=f"tc-{approval_id}",
        ),
    )
    assert isinstance(outcome, Committed)
    return outcome


async def _park(
    scope: Scope, notes: Registry, run: UUID, note_id: UUID, tool_call_id: str
) -> WaitingApproval:
    """Dispatch one `asks_first` write and insist it parked."""
    async with session(*scope) as scoped:
        outcome = await dispatch(
            _ctx(scoped, scope, notes, run, FakeClock()),
            _write(note_id, "parked", tool_call_id),
        )
        await scoped.commit()
    assert isinstance(outcome, WaitingApproval)
    return outcome


async def test_asks_first_opens_approval(scope: Scope, notes: Registry) -> None:
    run, note_id = uuid4(), uuid4()
    parked = await _park(scope, notes, run, note_id, "tc-park")

    async with session(*scope) as scoped:
        approval = await scoped.get(Approval, parked.approval_id)
        assert approval is not None
        assert approval.state == "requested"
        assert (approval.run_id, approval.step_no, approval.tool_call_id) == (
            run,
            1,
            "tc-park",
        )
        assert parked.expires_at == START + timedelta(hours=72)
        # The reservation stays open, so the parked call resumes under one key.
        assert await scoped.scalar(_reservation(run, "tc-park")) == 1
        assert await scoped.scalar(_NOTE_BODY, {"id": note_id}) is None


async def test_decide_approve_then_replay_commits(
    scope: Scope, notes: Registry
) -> None:
    clock = FakeClock()
    run, note_id = uuid4(), uuid4()
    parked = await _park(scope, notes, run, note_id, "tc-approve")

    async with session(*scope) as scoped:
        decided = await _decide(scoped, scope, clock, parked.approval_id, "approve")
        await scoped.commit()
        assert decided.result == {"decided": True, "state": "open", "run_queued": False}
        approval = await scoped.get(Approval, parked.approval_id)
        assert approval is not None
        assert (approval.state, approval.granted_by) == ("open", scope[1])

    async with session(*scope) as scoped:
        replay = await dispatch(
            _ctx(scoped, scope, notes, run, clock),
            _write(note_id, "parked", "tc-approve"),
        )
        await scoped.commit()
        assert isinstance(replay, Committed)
        assert replay.action is not None
        assert replay.action.approval_id == parked.approval_id
        spent = await scoped.get(Approval, parked.approval_id)
        assert spent is not None
        assert spent.state == "consumed"
        assert spent.consumed_by_action_id == replay.action.id
        assert await scoped.scalar(_NOTE_BODY, {"id": note_id}) == "parked"


async def test_approval_binds_to_digest(scope: Scope, notes: Registry) -> None:
    """Approved args are the only args: changed ones spend nothing and ask again."""
    clock = FakeClock()
    run, note_id = uuid4(), uuid4()
    parked = await _park(scope, notes, run, note_id, "tc-digest")

    async with session(*scope) as scoped:
        await _decide(scoped, scope, clock, parked.approval_id, "approve")
        await scoped.commit()

    async with session(*scope) as scoped:
        replay = await dispatch(
            _ctx(scoped, scope, notes, run, clock),
            _write(note_id, "something else", "tc-digest"),
        )
        await scoped.commit()
        # The open approval is untouched and the changed call is a new request.
        assert isinstance(replay, WaitingApproval)
        assert replay.approval_id != parked.approval_id
        approved = await scoped.get(Approval, parked.approval_id)
        assert approved is not None and approved.state == "open"
        assert await scoped.scalar(_NOTE_BODY, {"id": note_id}) is None


async def test_decide_reject_then_replay_denies(
    scope: Scope, notes: Registry
) -> None:
    clock = FakeClock()
    run, note_id = uuid4(), uuid4()
    parked = await _park(scope, notes, run, note_id, "tc-reject")

    async with session(*scope) as scoped:
        decided = await _decide(scoped, scope, clock, parked.approval_id, "reject")
        await scoped.commit()
        assert decided.result["state"] == "rejected"

    async with session(*scope) as scoped:
        replay = await dispatch(
            _ctx(scoped, scope, notes, run, clock),
            _write(note_id, "parked", "tc-reject"),
        )
        await scoped.commit()
        assert isinstance(replay, Denied)
        assert replay.reason == "approval_unavailable"
        assert replay.event.payload["state"] == "rejected"
        # The reason is the tool result the step continues with.
        assert replay.event.payload["approval_reason"] == "not this note"
        assert await scoped.scalar(_reservation(run, "tc-reject")) == 0
        assert await scoped.scalar(_NOTE_BODY, {"id": note_id}) is None


async def test_expired_approval_denied(scope: Scope, notes: Registry) -> None:
    """Past `expires_at` an open approval buys nothing, and an expired one denies."""
    clock = FakeClock()
    run, note_id = uuid4(), uuid4()
    parked = await _park(scope, notes, run, note_id, "tc-expire")

    async with session(*scope) as scoped:
        await _decide(scoped, scope, clock, parked.approval_id, "approve")
        await scoped.commit()

    clock.advance(timedelta(hours=72).total_seconds() + 1)
    async with session(*scope) as scoped:
        replay = await dispatch(
            _ctx(scoped, scope, notes, run, clock),
            _write(note_id, "parked", "tc-expire"),
        )
        await scoped.commit()
        assert isinstance(replay, WaitingApproval)
        assert await scoped.scalar(_NOTE_BODY, {"id": note_id}) is None

        # What wave 8's tick will do to that new request; then the step continues
        # with the denial as its tool result.
        stale = await scoped.get(Approval, replay.approval_id)
        assert stale is not None
        stale.state, stale.reason = "expired", "nobody answered"
        await scoped.flush()

        denied = await dispatch(
            _ctx(scoped, scope, notes, run, clock),
            _write(note_id, "parked", "tc-expire"),
        )
        await scoped.commit()
        assert isinstance(denied, Denied)
        assert denied.reason == "approval_unavailable"
        assert denied.event.payload["state"] == "expired"


async def test_decide_queues_a_waiting_run(scope: Scope, notes: Registry) -> None:
    clock = FakeClock()
    waiting, already_queued = uuid4(), uuid4()
    async with session(*scope) as scoped:
        for run, state in ((waiting, "waiting_approval"), (already_queued, "queued")):
            await scoped.execute(
                _RUN, {"run": run, "org": scope[0], "state": state}
            )
        await scoped.commit()

    parked = await _park(scope, notes, waiting, uuid4(), "tc-queue")
    async with session(*scope) as scoped:
        decided = await _decide(scoped, scope, clock, parked.approval_id, "approve")
        await scoped.commit()
        assert decided.result["run_queued"] is True
        assert await scoped.scalar(_RUN_STATE, {"run": waiting}) == "queued"
        assert await scoped.scalar(_QUEUED, {"run": waiting}) == 1

    # A run that is not waiting is decided and left alone: no second queue row.
    running = await _park(scope, notes, already_queued, uuid4(), "tc-no-queue")
    async with session(*scope) as scoped:
        decided = await _decide(scoped, scope, clock, running.approval_id, "approve")
        await scoped.commit()
        assert decided.result["decided"] is True
        assert decided.result["run_queued"] is False
        assert await scoped.scalar(_QUEUED, {"run": already_queued}) == 0
