"""The `tick` role: one leader, two chores — stale leases and dead approvals.

ADR-0011 makes `tick` a single leader, so a pass takes a Postgres advisory lock
before it moves anything. The lock is transaction-scoped: a pass that dies
mid-way releases it with its transaction instead of wedging every later tick.
Nothing here calls a model, and every approval it expires moves in a transaction
of its own, so one that cannot be handed back does not hold up the rest.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.kernel.identity.models import Approval
from app.kernel.runs.models import StepQueue
from app.kernel.runs.service import QUEUE_TAG
from app.kernel.runs.work import Clock, now
from app.kernel.store.models import Run
from app.kernel.store.service import Scope, session as open_session

# One deployment-wide key; any constant does, as long as only `tick` takes it.
LEADER_KEY = 0x41510008
# The reason an unanswered request carries, and the reason the resumed call then
# reads back out of dispatch's `approval_unavailable` denial.
EXPIRED = "expired"


@dataclass(frozen=True, slots=True)
class Pass:
    """What one tick pass moved."""

    reaped: int
    expired: int


async def tick_once(scope: Scope, *, clock: Clock = now) -> Pass | None:
    """One pass, or None when another process is already the leader."""
    async with open_session(*scope) as scoped:
        if not await _lead(scoped):
            return None
        reaped = await _reap(scoped, clock())
        await scoped.commit()
        return Pass(reaped, await _expire(scoped, clock()))


async def _lead(session: AsyncSession) -> bool:
    lock = select(func.pg_try_advisory_xact_lock(LEADER_KEY))
    return bool(await session.scalar(lock))


async def _reap(session: AsyncSession, when: datetime) -> int:
    """A lease past its expiry means the worker holding it is gone.

    Clearing the lease is what re-queues the step, and working it again is safe
    because every call the dead worker committed comes back from its reservation
    as `Replayed`.
    """
    reaped = await session.scalars(
        update(StepQueue)
        .where(StepQueue.lease_until <= when)
        .values(lease_until=None, claimed_by=None)
        .returning(StepQueue.run_id)
        .execution_options(synchronize_session=False)
    )
    return len(reaped.all())


async def _expire(session: AsyncSession, when: datetime) -> int:
    """Every request nobody answered in time, one transaction each."""
    stale = (
        await session.scalars(
            select(Approval).where(
                Approval.state == "requested", Approval.expires_at <= when
            )
        )
    ).all()
    expired = 0
    for approval in stale:
        if not await _lead(session):
            return expired
        expired += await _continue(session, approval)
        await session.commit()
    return expired


async def _continue(session: AsyncSession, approval: Approval) -> int:
    """`requested -> expired`, and the continuation a rejection would have got.

    The run moves only if it is still waiting on this answer, and the queue row
    goes in only when that guard matched, so a cancelled or already-running run
    is never enqueued twice. The resumed call finds no open approval and carries
    on with dispatch's `approval_unavailable` denial as its tool result.
    """
    # The lifecycle mutex first (runs/MODULE.md): the run row, then the approval,
    # the same order cancel takes them.
    await session.execute(
        select(Run.id).where(Run.id == approval.run_id).with_for_update()
    )
    moved = await session.scalar(
        update(Approval)
        .where(Approval.id == approval.id, Approval.state == "requested")
        .values(state=EXPIRED, reason=EXPIRED)
        .returning(Approval.id)
        .execution_options(synchronize_session=False)
    )
    if moved is None:
        return 0
    queued = await session.scalar(
        update(Run)
        .where(Run.id == approval.run_id, Run.state == "waiting_approval")
        .values(state="queued", updated_at=func.now())
        .returning(Run.id)
        .execution_options(synchronize_session=False)
    )
    if queued is not None:
        session.add(
            StepQueue(
                org_id=approval.org_id,
                run_id=approval.run_id,
                step_no=approval.step_no,
                queue_tag=QUEUE_TAG,
            )
        )
        await session.flush()
    return 1
