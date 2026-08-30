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
from datetime import datetime
from uuid import NAMESPACE_URL, UUID, uuid4, uuid5

from pydantic import BaseModel, ValidationError
from sqlalchemy import delete, select
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
from app.kernel.identity.models import Approval
from app.kernel.identity.service import (
    Consume,
    Park,
    args_hash,
    consume_approval,
    effective_grants,
    park_approval,
)

# `asks_first` is not here: it is a grant to ask, and the approval decides.
_REFUSAL = {None: "no_grant", "never": "never"}
_GRANTED = ("may_use", "asks_first")


class _UnapprovedError(Exception):
    """No open approval for this call; the savepoint's writes go back with it."""


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


@dataclass(frozen=True, slots=True)
class WaitingApproval:
    """A person has been asked. The reservation stays open and the step parks."""

    approval_id: UUID
    expires_at: datetime


Outcome = Committed | Replayed | Denied | WaitingApproval


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

    grants = await effective_grants(ctx.session, ctx.principal_id)
    level = grants.get(call.operation_name)
    if level not in _GRANTED:
        return await _deny(ctx, call, _REFUSAL[level], {"grant_level": level})

    try:
        args = op.args_model.model_validate(call.args)
    except ValidationError as invalid:
        errors = invalid.errors(include_url=False, include_context=False)
        return await _deny(ctx, call, "invalid_args", {"errors": errors})

    if op.mode == "read":
        return await _read(ctx, call, op, args, level)
    return await _write(ctx, call, op, args, level)


async def _write(
    ctx: CallContext, call: Call, op: Operation, args: BaseModel, level: str
) -> Outcome:
    if op.aggregate is not None and call.expected_version is None:
        return await _deny(ctx, call, "expected_version_required")

    version_id = ctx.registry.version_id(op)
    aggregate = _aggregate(op, args)
    action_id = uuid4()
    try:
        # The savepoint is what lets a conflict lose the body's writes and keep
        # the transaction: `commit()` raises before it has written anything. The
        # consume is inside it too, so a conflict leaves the approval open.
        async with ctx.session.begin_nested():
            approval_id = None
            if level == "asks_first":
                approval_id = await _spend(ctx, call, version_id, action_id)
                if approval_id is None:
                    raise _UnapprovedError
            result = await op.fn(ctx, args)
            action = await commit(
                ctx.session,
                Commit(
                    operation_version_id=version_id,
                    operation_name=op.name,
                    aggregate_kind=aggregate[0],
                    aggregate_id=aggregate[1],
                    expected_version=(
                        call.expected_version if op.aggregate is not None else None
                    ),
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
                    action_id=action_id,
                    approval_id=approval_id,
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
    except _UnapprovedError:
        return await _park(ctx, call, version_id)
    return Committed(action, result)


async def _read(
    ctx: CallContext, call: Call, op: Operation, args: BaseModel, level: str
) -> Outcome:
    """A read commits nothing and bumps no version; it leaves an audit event."""
    version_id = ctx.registry.version_id(op)
    if level == "asks_first" and await _spend(ctx, call, version_id, None) is None:
        return await _park(ctx, call, version_id)
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


async def _spend(
    ctx: CallContext, call: Call, version_id: str, action_id: UUID | None
) -> UUID | None:
    """The open approval this call spends, or None when there is none to spend."""
    return await consume_approval(
        ctx.session,
        Consume(
            granted_to=ctx.principal_id,
            operation_version_id=version_id,
            args_hash=args_hash(version_id, call.args),
            action_id=action_id,
            now=ctx.clock(),
        ),
    )


async def _park(ctx: CallContext, call: Call, version_id: str) -> Outcome:
    """Ask a person, unless this continuation was already answered."""
    if ctx.run_id is None or ctx.step_no is None:
        # An approval is addressed by the continuation it resumes at, so a call
        # made outside a run has nowhere to park and is refused instead.
        detail: Json = {"grant_level": "asks_first"}
        return await _deny(ctx, call, "approval_required", detail)
    parked = await park_approval(
        ctx.session,
        Park(
            granted_to=ctx.principal_id,
            operation_version_id=version_id,
            args_hash=args_hash(version_id, call.args),
            run_id=ctx.run_id,
            step_no=ctx.step_no,
            tool_call_id=call.tool_call_id,
            now=ctx.clock(),
        ),
    )
    if isinstance(parked, Approval):
        return WaitingApproval(parked.id, parked.expires_at)
    return await _deny(
        ctx,
        call,
        "approval_unavailable",
        # Not "reason": that key is the denial's own, and the payload carries both.
        {"state": parked.state, "approval_reason": parked.reason},
    )


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
