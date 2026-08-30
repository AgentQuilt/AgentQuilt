"""What dispatch guarantees: one run per call, a refusal on the record, no half-write.

Every test drives the toy module in `tests/kit_notes.py` through a scoped session,
because the grant, the org and the roles are what the guarantees rest on.
"""

from __future__ import annotations

from uuid import UUID, uuid4

import pytest
from sqlalchemy import Select, func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.kernel.declare.models import Action, Event, OperationVersion
from app.kernel.declare.registry import CallContext, Registry
from app.kernel.declare.service import Call, Committed, Denied, Replayed, dispatch
from app.kernel.store.service import session
from tests.kit import Scope, two_principals
from tests.kit_notes import grant, note_table, notes_registry

pytestmark = pytest.mark.anyio

WRITE = "note.write_note"
REMOVE = "note.remove_note"
LIST = "note.list_notes"

_NOTE_BODY = text("SELECT body FROM mod_test.note WHERE id = :id")
_RESERVATIONS = text(
    "SELECT count(*) FROM core.idempotency_key WHERE operation_name = :name"
)


@pytest.fixture(scope="module")
async def scopes(migrated_url: str) -> tuple[Scope, Scope]:
    return await two_principals(migrated_url)


@pytest.fixture(scope="module")
async def notes(migrated_url: str, scopes: tuple[Scope, Scope]) -> Registry:
    """The toy table, the operations published, and the grants the tests read.

    Org A may use all three. Org B is granted only `note.list_notes`, and only
    `asks_first`, so its lack of a write grant cannot depend on test order.
    """
    await note_table(migrated_url)
    registry = notes_registry()
    async with session(*scopes[0]) as scoped:
        await registry.publish(scoped)
        for name in (WRITE, REMOVE, LIST):
            await grant(scoped, scopes[0][1], name, "may_use")
        await scoped.commit()
    async with session(*scopes[1]) as scoped:
        await grant(scoped, scopes[1][1], LIST, "asks_first")
        await scoped.commit()
    return registry


def _ctx(
    scoped: AsyncSession, principal: UUID, registry: Registry, run: UUID
) -> CallContext:
    return CallContext(
        session=scoped,
        principal_id=principal,
        run_id=run,
        step_no=1,
        registry=registry,
    )


def _write(note_id: UUID, body: str, tool_call_id: str, version: int = 0) -> Call:
    return Call(
        operation_name=WRITE,
        args={"note_id": str(note_id), "body": body},
        tool_call_id=tool_call_id,
        expected_version=version,
    )


def _commits(aggregate: UUID) -> Select[tuple[int]]:
    return (
        select(func.count())
        .select_from(Event)
        .where(Event.aggregate_id == aggregate, Event.kind == "operation_commit")
    )


async def test_retry_returns_stored_action(
    scopes: tuple[Scope, Scope], notes: Registry
) -> None:
    org, principal = scopes[0]
    run, note_id = uuid4(), uuid4()
    call = _write(note_id, "first", "tc-retry")

    async with session(org, principal) as scoped:
        first = await dispatch(_ctx(scoped, principal, notes, run), call)
        await scoped.commit()
    assert isinstance(first, Committed)
    assert first.action is not None
    assert first.result == {"note_id": str(note_id)}

    async with session(org, principal) as scoped:
        again = await dispatch(_ctx(scoped, principal, notes, run), call)
        await scoped.commit()
        assert isinstance(again, Replayed)
        assert again.action.id == first.action.id
        assert await scoped.scalar(_NOTE_BODY, {"id": note_id}) == "first"
        assert await scoped.scalar(_commits(note_id)) == 1


async def test_denied_call_writes_denial_event(
    scopes: tuple[Scope, Scope], notes: Registry
) -> None:
    (org_a, principal_a), (org_b, principal_b) = scopes
    note_id = uuid4()

    async with session(org_b, principal_b) as scoped:
        outcome = await dispatch(
            _ctx(scoped, principal_b, notes, uuid4()),
            _write(note_id, "not allowed", "tc-denied"),
        )
        await scoped.commit()
        assert isinstance(outcome, Denied)
        assert outcome.reason == "no_grant"
        assert outcome.event.kind == "denial"
        assert outcome.event.payload["operation_name"] == WRITE
        assert await scoped.scalar(_NOTE_BODY, {"id": note_id}) is None
        # The reservation goes with the refusal, so a later retry is checked again.
        assert await scoped.scalar(_RESERVATIONS, {"name": WRITE}) == 0
        assert await scoped.get(Event, outcome.event.id) is not None

    async with session(org_a, principal_a) as scoped:
        assert await scoped.get(Event, outcome.event.id) is None


async def test_asks_first_without_a_run_is_denied(
    scopes: tuple[Scope, Scope], notes: Registry
) -> None:
    """An approval is addressed by a continuation, so a call outside a run cannot park.

    What an `asks_first` call inside a run does is `tests/test_approval_flow.py`.
    """
    org, principal = scopes[1]
    async with session(org, principal) as scoped:
        outcome = await dispatch(
            CallContext(
                session=scoped,
                principal_id=principal,
                run_id=None,
                step_no=None,
                registry=notes,
            ),
            Call(operation_name=LIST, args={}, tool_call_id="tc-asks"),
        )
        await scoped.commit()
        assert isinstance(outcome, Denied)
        assert outcome.reason == "approval_required"


async def test_version_conflict_rolls_the_operation_back(
    scopes: tuple[Scope, Scope], notes: Registry
) -> None:
    org, principal = scopes[0]
    note_id = uuid4()

    async with session(org, principal) as scoped:
        await dispatch(
            _ctx(scoped, principal, notes, uuid4()),
            _write(note_id, "first", "tc-conflict-a"),
        )
        await scoped.commit()

    async with session(org, principal) as scoped:
        outcome = await dispatch(
            _ctx(scoped, principal, notes, uuid4()),
            _write(note_id, "second", "tc-conflict-b"),
        )
        await scoped.commit()
        assert isinstance(outcome, Denied)
        assert outcome.reason == "version_conflict"
        assert outcome.event.payload["expected"] == 0
        assert outcome.event.payload["actual"] == 1
        # The savepoint is what makes this true: the body's insert is gone.
        assert await scoped.scalar(_NOTE_BODY, {"id": note_id}) == "first"
        assert await scoped.scalar(_commits(note_id)) == 1


async def test_read_appends_audit_and_no_action(
    scopes: tuple[Scope, Scope], notes: Registry
) -> None:
    org, principal = scopes[0]
    async with session(org, principal) as scoped:
        outcome = await dispatch(
            _ctx(scoped, principal, notes, uuid4()),
            Call(operation_name=LIST, args={}, tool_call_id="tc-read"),
        )
        await scoped.commit()
        assert isinstance(outcome, Committed)
        assert outcome.action is None
        assert isinstance(outcome.result["bodies"], list)

        audits = await scoped.scalar(
            select(func.count())
            .select_from(Event)
            .where(Event.kind == "read_audit", Event.operation_name == LIST)
        )
        assert audits == 1
        actions = await scoped.scalar(
            select(func.count())
            .select_from(Action)
            .join(Event, Event.action_id == Action.id)
            .where(Event.operation_name == LIST)
        )
        assert actions == 0


async def test_compensator_args_are_the_result(
    scopes: tuple[Scope, Scope], notes: Registry
) -> None:
    org, principal = scopes[0]
    note_id = uuid4()

    async with session(org, principal) as scoped:
        written = await dispatch(
            _ctx(scoped, principal, notes, uuid4()),
            _write(note_id, "compensate me", "tc-comp-write"),
        )
        await scoped.commit()
    assert isinstance(written, Committed)
    assert written.action is not None
    assert written.action.compensator_ref == REMOVE
    compensator_args = written.action.compensator_args
    assert compensator_args is not None
    assert compensator_args == {"note_id": str(note_id)}

    async with session(org, principal) as scoped:
        undone = await dispatch(
            _ctx(scoped, principal, notes, uuid4()),
            Call(
                operation_name=REMOVE,
                args=compensator_args,
                tool_call_id="tc-comp-remove",
                expected_version=1,
            ),
        )
        await scoped.commit()
        assert isinstance(undone, Committed)
        assert await scoped.scalar(_NOTE_BODY, {"id": note_id}) is None


async def test_published_version_matches_action(
    scopes: tuple[Scope, Scope], notes: Registry
) -> None:
    org, principal = scopes[0]
    async with session(org, principal) as scoped:
        await notes.publish(scoped)
        outcome = await dispatch(
            _ctx(scoped, principal, notes, uuid4()),
            _write(uuid4(), "published", "tc-published"),
        )
        await scoped.commit()
        assert isinstance(outcome, Committed)
        assert outcome.action is not None
        version_id = outcome.action.operation_version_id
        version = await scoped.get(OperationVersion, version_id)
        assert version is not None
        assert version.declaration["name"] == WRITE
