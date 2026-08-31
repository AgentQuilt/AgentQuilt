"""The ledger's two writes: `commit()` for an operation, `append()` for the rest.

Both run inside the caller's transaction and read the org from the session, so a
caller cannot write into an org it did not open the session with. Both switch the
connection to `agentquilt_ledger_writer` for their writes only and back to
`agentquilt_app` before returning: the app role may read the ledger and never
write it, which is what makes the append-only claim hold against application code.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal
from uuid import UUID, uuid4

from sqlalchemy import select, text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.kernel.declare.models import (
    Action,
    Event,
    IdempotencyKey,
    Json,
    StreamHead,
)

_WRITER = text("SET LOCAL ROLE agentquilt_ledger_writer")
_APP = text("SET LOCAL ROLE agentquilt_app")


@dataclass(frozen=True, slots=True)
class Commit:
    """One operation's write: the event, its action, and its idempotency key."""

    operation_version_id: str
    operation_name: str
    aggregate_kind: str
    aggregate_id: UUID
    expected_version: int | None
    principal_id: UUID
    run_id: UUID | None
    step_no: int | None
    idempotency_key: str
    payload: Json
    decision_trace: Json
    compensator_ref: str | None = None
    compensator_args: Json | None = None
    # `action` is append-only, so an action that names the approval it spent has
    # to know both ids before its INSERT: dispatch names the action here, then
    # consumes the approval against that id inside the same savepoint.
    action_id: UUID | None = None
    approval_id: UUID | None = None


@dataclass(frozen=True, slots=True)
class Append:
    """A ledger event that is not an operation: no action, no version bump."""

    kind: Literal["run_journal", "read_audit", "denial"]
    aggregate_kind: str
    aggregate_id: UUID
    principal_id: UUID
    payload: Json
    run_id: UUID | None
    step_no: int | None
    operation_name: str | None = None


@dataclass(frozen=True)
class VersionConflictError(Exception):
    """`expected_version` did not match the aggregate's stream head."""

    expected: int
    actual: int


async def commit(session: AsyncSession, request: Commit) -> Action:
    org = UUID(session.info["org"])
    stored = await session.scalar(
        select(Action)
        .join(IdempotencyKey, IdempotencyKey.action_id == Action.id)
        .where(
            IdempotencyKey.org_id == org,
            IdempotencyKey.operation_name == request.operation_name,
            IdempotencyKey.idempotency_key == request.idempotency_key,
        )
    )
    if stored is not None:
        return stored

    # The lock is what serialises two commits on one aggregate: the second reads
    # the first's version only after it lands, and then disagrees with its caller.
    head = await session.get(
        StreamHead,
        (org, request.aggregate_kind, request.aggregate_id),
        with_for_update=True,
    )
    actual = head.version if head is not None else 0
    # None = the operation declares no aggregate: unversioned, no check (ADR-0017).
    if request.expected_version is not None and actual != request.expected_version:
        raise VersionConflictError(request.expected_version, actual)

    # The reads above are the app role's; only the writes need the ledger writer,
    # and a flush that fails leaves a dead transaction whose rollback resets the role.
    await session.execute(_WRITER)
    action_id = request.action_id or uuid4()
    event = Event(
        org_id=org,
        kind="operation_commit",
        aggregate_kind=request.aggregate_kind,
        aggregate_id=request.aggregate_id,
        aggregate_version=actual + 1,
        run_id=request.run_id,
        step_no=request.step_no,
        principal_id=request.principal_id,
        operation_name=request.operation_name,
        payload=request.payload,
        action_id=action_id,
    )
    session.add(event)
    # The event first, because stream_head.last_event_id points at it; the action
    # after, which the deferred fk_event_action allows and COMMIT then checks.
    await session.flush()

    if head is None:
        session.add(
            StreamHead(
                org_id=org,
                aggregate_kind=request.aggregate_kind,
                aggregate_id=request.aggregate_id,
                version=1,
                last_event_id=event.id,
            )
        )
    else:
        head.version = actual + 1
        head.last_event_id = event.id

    action = Action(
        id=action_id,
        org_id=org,
        event_id=event.id,
        operation_version_id=request.operation_version_id,
        approval_id=request.approval_id,
        idempotency_key=request.idempotency_key,
        decision_trace=request.decision_trace,
        compensator_ref=request.compensator_ref,
        compensator_args=request.compensator_args,
    )
    session.add(action)
    # Dispatch reserves the key (`action_id` NULL) before it runs the operation, so
    # the usual path here is completing that reservation; a caller with no
    # reservation inserts. The `where` is what keeps a key that already names an
    # action pointing at that one.
    await session.execute(
        insert(IdempotencyKey)
        .values(
            org_id=org,
            operation_name=request.operation_name,
            idempotency_key=request.idempotency_key,
            action_id=action_id,
        )
        .on_conflict_do_update(
            # The inferred set is the primary key, which grew the plane in 0004:
            # a DEV replay must not match a PROD reservation.
            index_elements=[
                IdempotencyKey.environment_id,
                IdempotencyKey.org_id,
                IdempotencyKey.operation_name,
                IdempotencyKey.idempotency_key,
            ],
            set_={"action_id": action_id},
            where=IdempotencyKey.action_id.is_(None),
        )
    )
    await session.flush()
    await session.execute(_APP)
    return action


async def append(session: AsyncSession, request: Append) -> Event:
    await session.execute(_WRITER)
    event = Event(
        org_id=UUID(session.info["org"]),
        kind=request.kind,
        aggregate_kind=request.aggregate_kind,
        aggregate_id=request.aggregate_id,
        aggregate_version=0,
        run_id=request.run_id,
        step_no=request.step_no,
        principal_id=request.principal_id,
        operation_name=request.operation_name,
        payload=request.payload,
    )
    session.add(event)
    await session.flush()
    await session.execute(_APP)
    return event
