"""Who a caller is, what they may do, and what an approval is bound to.

A pure function over the two tables, with no port and no policy engine behind it
(ADR-0026): dispatch is the only caller, so when a second evaluator ever appears
these inputs can be serialised without a module changing. The two approval
functions are the other half of that call: dispatch consumes an open approval or
parks the call, both inside its own transaction.
"""

from __future__ import annotations

import hashlib
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, cast
from uuid import UUID, uuid4

import rfc8785
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.kernel.declare.models import Json
from app.kernel.identity.models import Approval, Grant
from app.kernel.store.models import Principal, UserToken

# Prefixed and separated so a hash over one field's value can never collide with
# a hash over another's (ADR-0004, the consume-once predicate).
_DOMAIN = b"agentquilt.approval.v1"
_SEPARATOR = b"\x00"
# A request a human never answers stops being answerable; `tick` expires it.
_LIFETIME = timedelta(hours=72)
# States a parked call may already have been left in; the rest mean it moved on.
_PARKED = ("requested", "rejected", "expired")


async def resolve(session: AsyncSession, token: str) -> Principal | None:
    """The user principal a live token names, or None for revoked and unknown."""
    return await session.scalar(
        select(Principal)
        .join(UserToken, UserToken.user_id == Principal.user_id)
        .where(
            UserToken.token_hash == hashlib.sha256(token.encode()).hexdigest(),
            UserToken.revoked_at.is_(None),
            Principal.class_ == "user",
        )
    )


async def effective_grants(
    session: AsyncSession, principal_id: UUID
) -> Mapping[str, str]:
    """The acting principal's own grants, one term of ADR-0015's intersection.

    The full formula — root ceiling ∩ narrowing state (always empty in Phase 1)
    ∩ these grants — is applied at dispatch, which intersects this mapping with
    the run's stored ceiling for any call made inside a run.
    """
    rows = await session.execute(
        select(Grant.operation_name, Grant.level).where(
            Grant.principal_id == principal_id
        )
    )
    return {name: level for name, level in rows}


def args_hash(operation_version_id: str, args: Json, scope: str = "") -> str:
    """What an approval is bound to: this operation version, these args, this scope."""
    # The ledger types a payload `dict[str, object]` and rfc8785 types the same
    # JSON shape recursively; `dumps` raises on anything that is not JSON, so the
    # cast is checked by the call it feeds.
    canonical = rfc8785.dumps(cast("Mapping[str, Any]", args))
    parts = (_DOMAIN, operation_version_id.encode(), canonical, scope.encode())
    return hashlib.sha256(_SEPARATOR.join(parts)).hexdigest()


@dataclass(frozen=True, slots=True)
class Consume:
    """The consume-once predicate's four bindings, and the action that claims it."""

    granted_to: UUID
    operation_version_id: str
    args_hash: str
    # None for a read: an approved read commits no action to point back at.
    action_id: UUID | None
    now: datetime


@dataclass(frozen=True, slots=True)
class Park:
    """One call waiting on a human, identified by the continuation it resumes at."""

    granted_to: UUID
    operation_version_id: str
    args_hash: str
    run_id: UUID
    step_no: int
    tool_call_id: str
    now: datetime


@dataclass(frozen=True, slots=True)
class Decided:
    """This continuation was already answered; the reason becomes the tool result."""

    state: str
    reason: str | None


# An `Approval` here is always `requested`, whether this call opened it or found it.
ParkOutcome = Approval | Decided


async def consume_approval(session: AsyncSession, request: Consume) -> UUID | None:
    """Spend one open approval, or None. Consumed once: a second call gets None.

    ADR-0004: the predicate carries the org, the principal, the operation version
    and the domain-separated args hash, so an approval cannot be spent across any
    of the four. It is one statement, so two callers racing it cannot both win.
    """
    return await session.scalar(
        update(Approval)
        .where(
            Approval.org_id == UUID(session.info["org"]),
            Approval.granted_to == request.granted_to,
            Approval.operation_version_id == request.operation_version_id,
            Approval.args_hash == request.args_hash,
            Approval.state == "open",
            Approval.expires_at > request.now,
        )
        .values(state="consumed", consumed_by_action_id=request.action_id)
        .returning(Approval.id)
        .execution_options(synchronize_session=False)
    )


async def park_approval(session: AsyncSession, request: Park) -> ParkOutcome:
    """Ask a human, or report the answer this continuation already got."""
    existing = await session.scalar(
        select(Approval).where(
            Approval.run_id == request.run_id,
            Approval.step_no == request.step_no,
            Approval.tool_call_id == request.tool_call_id,
            Approval.state.in_(_PARKED),
        )
    )
    if existing is not None:
        if existing.state == "requested":
            return existing
        return Decided(existing.state, existing.reason)

    approval = Approval(
        id=uuid4(),
        org_id=UUID(session.info["org"]),
        granted_to=request.granted_to,
        operation_version_id=request.operation_version_id,
        args_hash=request.args_hash,
        state="requested",
        run_id=request.run_id,
        step_no=request.step_no,
        tool_call_id=request.tool_call_id,
        expires_at=request.now + _LIFETIME,
    )
    session.add(approval)
    await session.flush()
    return approval
