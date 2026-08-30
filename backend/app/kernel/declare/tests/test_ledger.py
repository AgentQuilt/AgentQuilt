"""What the ledger guarantees: no lone commit, one version per write, one action.

Every test goes through a scoped session, because the org and the role are what
the guarantees rest on; nothing here reaches the database another way.
"""

from __future__ import annotations

from uuid import UUID, uuid4

import pytest
from sqlalchemy import Select, func, select, text
from sqlalchemy.exc import IntegrityError, ProgrammingError

from app.kernel.declare.ledger import Append, Commit, VersionConflict, append, commit
from app.kernel.declare.models import Event, OperationVersion, StreamHead
from app.kernel.store.service import session
from tests.kit import Scope, two_principals

pytestmark = pytest.mark.anyio

WRITER = text("SET LOCAL ROLE agentquilt_ledger_writer")
OPERATION = "test.write"
OPERATION_VERSION = "opv-test"


@pytest.fixture(scope="module")
async def scopes(migrated_url: str) -> tuple[Scope, Scope]:
    return await two_principals(migrated_url)


@pytest.fixture(scope="module")
async def declared(scopes: tuple[Scope, Scope]) -> None:
    """The operation every action here points at; the app role owns this table."""
    async with session(*scopes[0]) as scoped:
        scoped.add(
            OperationVersion(
                id=OPERATION_VERSION,
                operation_name=OPERATION,
                stage="DEV",
                declaration={},
            )
        )
        await scoped.commit()


def _request(principal: UUID, aggregate: UUID, expected: int, *, key: str) -> Commit:
    return Commit(
        operation_version_id=OPERATION_VERSION,
        operation_name=OPERATION,
        aggregate_kind="thing",
        aggregate_id=aggregate,
        expected_version=expected,
        principal_id=principal,
        run_id=None,
        step_no=None,
        idempotency_key=key,
        payload={"version": expected + 1},
        decision_trace={},
    )


def _events(aggregate: UUID) -> Select[tuple[int]]:
    """How many events that aggregate has, whoever the reading session is."""
    return (
        select(func.count()).select_from(Event).where(Event.aggregate_id == aggregate)
    )


async def test_app_role_cannot_insert_event(scopes: tuple[Scope, Scope]) -> None:
    org, principal = scopes[0]
    async with session(org, principal) as scoped:
        scoped.add(
            Event(
                org_id=org,
                kind="run_journal",
                aggregate_kind="thing",
                aggregate_id=uuid4(),
                aggregate_version=0,
                principal_id=principal,
                payload={},
            )
        )
        with pytest.raises(ProgrammingError, match="permission denied"):
            await scoped.flush()


async def test_commit_without_action_impossible(scopes: tuple[Scope, Scope]) -> None:
    org, principal = scopes[0]

    def _commit_event(action_id: UUID | None) -> Event:
        return Event(
            org_id=org,
            kind="operation_commit",
            aggregate_kind="thing",
            aggregate_id=uuid4(),
            aggregate_version=1,
            principal_id=principal,
            operation_name=OPERATION,
            payload={},
            action_id=action_id,
        )

    async with session(org, principal) as scoped:
        await scoped.execute(WRITER)
        scoped.add(_commit_event(None))
        with pytest.raises(IntegrityError, match="ck_event_action_id_by_kind"):
            await scoped.flush()

    async with session(org, principal) as scoped:
        await scoped.execute(WRITER)
        scoped.add(_commit_event(uuid4()))
        await scoped.flush()
        with pytest.raises(IntegrityError, match="fk_event_action"):
            await scoped.commit()


async def test_expected_version_mismatch_rolls_back(
    scopes: tuple[Scope, Scope], declared: None
) -> None:
    org, principal = scopes[0]
    aggregate = uuid4()
    async with session(org, principal) as scoped:
        await commit(scoped, _request(principal, aggregate, 0, key="first"))
        await scoped.commit()

    async with session(org, principal) as scoped:
        with pytest.raises(VersionConflict) as conflict:
            await commit(scoped, _request(principal, aggregate, 0, key="stale"))
        assert conflict.value == VersionConflict(0, 1)
        await scoped.rollback()

        assert await scoped.scalar(_events(aggregate)) == 1
        head = await scoped.get(StreamHead, (org, "thing", aggregate))
        assert head is not None and head.version == 1

        await commit(scoped, _request(principal, aggregate, 1, key="second"))
        await scoped.commit()
        assert await scoped.scalar(_events(aggregate)) == 2
        assert await scoped.scalar(
            select(StreamHead.version).where(StreamHead.aggregate_id == aggregate)
        ) == 2


async def test_retry_returns_stored_action(
    scopes: tuple[Scope, Scope], declared: None
) -> None:
    org, principal = scopes[0]
    aggregate = uuid4()
    request = _request(principal, aggregate, 0, key="once")
    async with session(org, principal) as scoped:
        first = await commit(scoped, request)
        await scoped.commit()
        action_id = first.id

    async with session(org, principal) as scoped:
        again = await commit(scoped, request)
        assert again.id == action_id
        await scoped.commit()
        assert await scoped.scalar(_events(aggregate)) == 1


async def test_append_writes_a_journal_event_without_action(
    scopes: tuple[Scope, Scope],
) -> None:
    (org, principal), (other_org, other_principal) = scopes
    aggregate = uuid4()
    async with session(org, principal) as scoped:
        event = await append(
            scoped,
            Append(
                kind="run_journal",
                aggregate_kind="thing",
                aggregate_id=aggregate,
                principal_id=principal,
                payload={"note": "started"},
                run_id=uuid4(),
                step_no=1,
            ),
        )
        await scoped.commit()
        assert event.action_id is None
        assert event.aggregate_version == 0
        assert await scoped.scalar(_events(aggregate)) == 1

    async with session(other_org, other_principal) as scoped:
        assert await scoped.scalar(_events(aggregate)) == 0
