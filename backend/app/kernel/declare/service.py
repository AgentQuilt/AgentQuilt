"""Dispatch: the one way a declared operation runs, and the only way it is refused.

Every call takes the same order of checks — the operation exists, the reservation is
fresh, the principal is granted it, the args parse, and only then the body runs — and
every refusal leaves a `denial` event behind, so a call that did nothing is as
readable in the ledger as one that did. Dispatch runs inside the caller's
transaction; the operation's own writes sit in a savepoint, so a version conflict
rolls the body back without touching the denial that records it.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from uuid import NAMESPACE_URL, UUID, uuid5

from pydantic import BaseModel, ValidationError
from sqlalchemy import delete, select, text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.kernel.declare.ledger import (
    Append,
    Commit,
    VersionConflictError,
    append,
    commit,
)
from app.kernel.declare.models import Action, Event, IdempotencyKey, Json
from app.kernel.declare.registry import CallContext, Operation

# Wave 5 replaces this with `identity.effective_grants`, which resolves roles and
# scope; until then a grant is one row read straight off the table.
_GRANT = text(
    'SELECT level FROM core."grant"'
    " WHERE principal_id = :principal AND operation_name = :name LIMIT 1"
)
_REFUSAL = {None: "no_grant", "never": "never", "asks_first": "approval_required"}


@dataclass(frozen=True, slots=True)
class Call:
    """One tool call as the model made it, before anything is known about it."""

    operation_name: str
    args: Json
    tool_call_id: str
    expected_version: int | None = None


@dataclass(frozen=True, slots=True)
class Committed:
    """The operation ran; `action` is None for a read, which commits nothing."""

    action: Action | None
    result: Json


@dataclass(frozen=True, slots=True)
class Replayed:
    """The same call already committed; its action is returned, nothing runs."""

    action: Action


@dataclass(frozen=True, slots=True)
class Denied:
    """The call was refused; `event` is the denial the ledger now carries."""

    reason: str
    event: Event


Outcome = Committed | Replayed | Denied


async def dispatch(ctx: CallContext, call: Call) -> Outcome:
    try:
        op = ctx.registry.get(call.operation_name)
    except KeyError:
        return await _deny(ctx, call, "unknown_operation")

    stored = await _reserve(
        ctx.session, call.operation_name, _idempotency_key(ctx, call)
    )
    if stored is not None:
        return Replayed(stored)

    level = await _grant_level(ctx.session, ctx.principal_id, call.operation_name)
    if level != "may_use":
        return await _deny(ctx, call, _REFUSAL[level], {"grant_level": level})

    try:
        args = op.args_model.model_validate(call.args)
    except ValidationError as invalid:
        return await _deny(ctx, call, "invalid_args", {"errors": invalid.errors()})

    if op.mode == "read":
        return await _read(ctx, op, args)
    return await _write(ctx, call, op, args, level)


async def _write(
    ctx: CallContext, call: Call, op: Operation, args: BaseModel, level: str
) -> Outcome:
    if op.aggregate is not None and call.expected_version is None:
        return await _deny(ctx, call, "expected_version_required")

    version_id = ctx.registry.version_id(op)
    aggregate = _aggregate(op, args)
    try:
        # The savepoint is what lets a conflict lose the body's writes and keep
        # the transaction: `commit()` raises before it has written anything.
        async with ctx.session.begin_nested():
            result = await op.fn(ctx, args)
            action = await commit(
                ctx.session,
                Commit(
                    operation_version_id=version_id,
                    operation_name=op.name,
                    aggregate_kind=aggregate[0],
                    aggregate_id=aggregate[1],
                    expected_version=call.expected_version or 0,
                    principal_id=ctx.principal_id,
                    run_id=ctx.run_id,
                    step_no=ctx.step_no,
                    idempotency_key=_idempotency_key(ctx, call),
                    payload={"args": args.model_dump(mode="json"), "result": result},
                    decision_trace={
                        "grant_level": level,
                        "operation_version_id": version_id,
                    },
                    compensator_ref=op.compensator,
                    # A compensator's args model accepts its target's result.
                    compensator_args=result,
                ),
            )
    except VersionConflictError as conflict:
        return await _deny(
            ctx,
            call,
            "version_conflict",
            {"expected": conflict.expected, "actual": conflict.actual},
            aggregate,
        )
    return Committed(action, result)


async def _read(ctx: CallContext, op: Operation, args: BaseModel) -> Committed:
    """A read commits nothing and bumps no version; it leaves an audit event."""
    result = await op.fn(ctx, args)
    kind, aggregate_id = _aggregate(op, args)
    await append(
        ctx.session,
        Append(
            kind="read_audit",
            aggregate_kind=kind,
            aggregate_id=aggregate_id,
            principal_id=ctx.principal_id,
            payload={"args": args.model_dump(mode="json")},
            run_id=ctx.run_id,
            step_no=ctx.step_no,
            operation_name=op.name,
        ),
    )
    return Committed(None, result)


async def _deny(
    ctx: CallContext,
    call: Call,
    reason: str,
    detail: Json | None = None,
    aggregate: tuple[str, UUID] | None = None,
) -> Denied:
    # The reservation goes with the refusal: a call retried later is checked again.
    await ctx.session.execute(
        delete(IdempotencyKey).where(
            IdempotencyKey.operation_name == call.operation_name,
            IdempotencyKey.idempotency_key == _idempotency_key(ctx, call),
        )
    )
    kind, aggregate_id = aggregate or ("operation", _operation_id(call.operation_name))
    event = await append(
        ctx.session,
        Append(
            kind="denial",
            aggregate_kind=kind,
            aggregate_id=aggregate_id,
            principal_id=ctx.principal_id,
            payload={
                "reason": reason,
                "operation_name": call.operation_name,
                "tool_call_id": call.tool_call_id,
                **(detail or {}),
            },
            run_id=ctx.run_id,
            step_no=ctx.step_no,
            operation_name=call.operation_name,
        ),
    )
    return Denied(reason, event)


async def _reserve(session: AsyncSession, name: str, key: str) -> Action | None:
    """Claim the key before the body runs; the stored action means a replay."""
    await session.execute(
        insert(IdempotencyKey)
        .values(
            org_id=UUID(session.info["org"]),
            operation_name=name,
            idempotency_key=key,
            action_id=None,
        )
        .on_conflict_do_nothing()
    )
    return await session.scalar(
        select(Action)
        .join(IdempotencyKey, IdempotencyKey.action_id == Action.id)
        .where(
            IdempotencyKey.operation_name == name,
            IdempotencyKey.idempotency_key == key,
        )
    )


async def _grant_level(
    session: AsyncSession, principal_id: UUID, name: str
) -> str | None:
    return await session.scalar(_GRANT, {"principal": principal_id, "name": name})


def _aggregate(op: Operation, args: BaseModel) -> tuple[str, UUID]:
    if op.aggregate is None:
        return "operation", _operation_id(op.name)
    kind, path = op.aggregate
    return kind, UUID(str(getattr(args, path)))


def _operation_id(name: str) -> UUID:
    """An operation with no aggregate still needs one stream to be read on."""
    return uuid5(NAMESPACE_URL, name)


def _idempotency_key(ctx: CallContext, call: Call) -> str:
    digest = f"{ctx.run_id}:{ctx.step_no}:{call.tool_call_id}"
    return hashlib.sha256(digest.encode()).hexdigest()
