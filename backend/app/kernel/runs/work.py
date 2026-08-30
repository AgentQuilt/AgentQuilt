"""The `work` role: claim one step, work it, leave the run ready for the next.

Two transactions per cycle, because ADR-0019 forbids a model call inside a claim:
the first takes the lease under `FOR UPDATE SKIP LOCKED` and commits, the second
does the whole step — drain, assemble, model, plan, dispatch, checkpoint,
re-enqueue — and commits once. A worker that dies leaves its lease behind; `tick`
clears it and the step is worked again under the same reservation keys, so every
call the dead worker committed comes back from dispatch as `Replayed` and nothing
runs twice.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from sqlalchemy import delete, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.kernel.context.service import Call as TurnCall, assemble
from app.kernel.declare.ledger import Append, append
from app.kernel.declare.models import StreamHead
from app.kernel.declare.registry import CallContext, Registry
from app.kernel.declare.service import (
    Call as ToolCall,
    Committed,
    Denied,
    Replayed,
    WaitingApproval,
    dispatch,
)
from app.kernel.model import service as model
from app.kernel.ports.model_runner import Completion, ModelRunner, ProposedCall
from app.kernel.runs.models import Checkpoint, MailboxMessage, StepQueue
from app.kernel.runs.service import AGGREGATE, QUEUE_TAG, post
from app.kernel.store.models import Json, Run
from app.kernel.store.service import session as open_session

Clock = Callable[[], datetime]
Scope = tuple[UUID, UUID]

# How long a claim is good for. Longer than a step and short enough that a dead
# worker's step is picked up while the person who started it is still watching.
LEASE = timedelta(minutes=5)
# The journal event that carries the model's plan, before any of it runs.
PLANNED = "step.planned"
# A run whose worker died is `running` with a stale lease, and claimable again.
_CLAIMABLE = ("queued", "running")
# Dispatch's own denial reason for a lost version race; the notice it earns is a
# mailbox message, so the model reads it on the next step.
_CONFLICT = "version_conflict"


def now() -> datetime:
    """The wall clock the worker reads; tests hand in `FakeClock.now` instead."""
    return datetime.now(UTC)


@dataclass(frozen=True, slots=True)
class Claimed:
    """One step this worker holds a lease on."""

    run_id: UUID
    step_no: int


async def claim(
    session: AsyncSession, *, worker_id: str, now: datetime
) -> Claimed | None:
    """Take one free step on a lease, or None when the queue has nothing free.

    `SKIP LOCKED` is what lets N workers run the same statement: a row another
    worker is claiming right now is not a row this one waits for. Nothing here
    calls a model — the caller commits this transaction and then works the step.
    """
    row = (
        await session.execute(
            select(StepQueue.run_id, StepQueue.step_no)
            .join(Run, Run.id == StepQueue.run_id)
            .where(
                StepQueue.queue_tag == QUEUE_TAG,
                Run.state.in_(_CLAIMABLE),
                or_(StepQueue.lease_until.is_(None), StepQueue.lease_until <= now),
            )
            .order_by(StepQueue.step_no, StepQueue.run_id)
            .limit(1)
            .with_for_update(skip_locked=True, of=StepQueue)
        )
    ).first()
    if row is None:
        return None
    run_id, step_no = row
    await session.execute(
        update(StepQueue)
        .where(StepQueue.run_id == run_id, StepQueue.step_no == step_no)
        .values(lease_until=now + LEASE, claimed_by=worker_id)
        .execution_options(synchronize_session=False)
    )
    await session.execute(
        update(Run)
        .where(Run.id == run_id)
        .values(state="running", updated_at=func.now())
        .execution_options(synchronize_session=False)
    )
    return Claimed(run_id, step_no)


async def step(
    session: AsyncSession,
    claimed: Claimed,
    *,
    runner: ModelRunner,
    registry: Registry,
    clock: Clock,
) -> str:
    """Work one claimed step and return the run's state after it.

    One transaction: the plan, the calls it dispatched, the checkpoint and the
    next queue row land together or not at all.
    """
    run = await session.get_one(Run, claimed.run_id)
    seen, drained = await _drain(session, run.id)
    assembled = await assemble(
        session,
        run,
        claimed.step_no,
        call=TurnCall(
            # The run's cap is also this turn's prompt budget: Phase 1 has one
            # model call per step, so a turn that would not fit under the cap
            # could not be paid for either.
            budget_tokens=run.budget_cap_tokens,
            intake=_intake(drained),
        ),
        registry=registry,
    )
    answered = await model.run(session, assembled, run, runner=runner)
    if isinstance(answered, model.Refused):
        # Terminal, and no checkpoint: nothing was bought, so there is nothing to
        # resume from, and a person starts a new run rather than the worker
        # retrying against a cap that has not moved.
        await session.execute(
            delete(StepQueue).where(
                StepQueue.run_id == run.id, StepQueue.step_no == claimed.step_no
            )
        )
        return await _state(session, run, "failed", answered.reason)
    await _journal(session, run.id, claimed.step_no, answered.completion)
    context = CallContext(
        session=session,
        principal_id=UUID(session.info["principal"]),
        run_id=run.id,
        step_no=claimed.step_no,
        registry=registry,
        clock=clock,
    )
    results, parked = await _dispatch_all(context, run.id, answered.completion.calls)
    return await _settle(
        session,
        run,
        claimed.step_no,
        _Step(
            text=answered.completion.text,
            results=results,
            parked=parked,
            mailbox_seq=drained[-1].seq if drained else seen,
        ),
    )


async def work_once(
    scope: Scope,
    *,
    worker_id: str,
    runner: ModelRunner,
    registry: Registry,
    clock: Clock = now,
) -> str | None:
    """One claim-work cycle: the run's state after it, or None if nothing was free."""
    async with open_session(*scope) as scoped:
        claimed = await claim(scoped, worker_id=worker_id, now=clock())
        await scoped.commit()
    if claimed is None:
        return None
    async with open_session(*scope) as scoped:
        state = await step(
            scoped, claimed, runner=runner, registry=registry, clock=clock
        )
        await scoped.commit()
        return state


@dataclass(frozen=True, slots=True)
class _Step:
    """What the step produced, for the checkpoint and the run's next state."""

    text: str
    results: list[Json]
    parked: bool
    mailbox_seq: int


async def _settle(
    session: AsyncSession, run: Run, step_no: int, outcome: _Step
) -> str:
    """How the step ends: parked, answered, or handed on to the next step."""
    # ADR-0019: a worked step's row is deleted, and its history is in the journal.
    await session.execute(
        delete(StepQueue).where(
            StepQueue.run_id == run.id, StepQueue.step_no == step_no
        )
    )
    if outcome.parked:
        # No checkpoint: the same step number is re-queued by whoever answers the
        # approval, and it must drain the same mailbox and replay the same calls.
        return await _state(session, run, "waiting_approval")
    session.add(
        Checkpoint(
            id=uuid4(),
            org_id=run.org_id,
            run_id=run.id,
            step_no=step_no,
            state={
                "mailbox_seq": outcome.mailbox_seq,
                "text": outcome.text,
                "results": outcome.results,
            },
        )
    )
    if not outcome.results:
        # A turn that proposed no call has said what it had to say.
        return await _state(session, run, "done")
    session.add(
        StepQueue(
            org_id=run.org_id,
            run_id=run.id,
            step_no=step_no + 1,
            queue_tag=QUEUE_TAG,
        )
    )
    return await _state(session, run, "queued")


async def _state(
    session: AsyncSession, run: Run, state: str, reason: str | None = None
) -> str:
    await session.execute(
        update(Run)
        .where(Run.id == run.id)
        .values(state=state, failure_reason=reason, updated_at=func.now())
        .execution_options(synchronize_session=False)
    )
    await session.flush()
    return state


async def _dispatch_all(
    context: CallContext, run_id: UUID, calls: tuple[ProposedCall, ...]
) -> tuple[list[Json], bool]:
    """Dispatch the plan in order, stopping at the first call that parks."""
    results: list[Json] = []
    for proposed in calls:
        outcome = await dispatch(
            context,
            ToolCall(
                operation_name=proposed.name,
                args=proposed.args,
                tool_call_id=proposed.tool_call_id,
                expected_version=await _expected_version(
                    context.session, context.registry, proposed
                ),
            ),
        )
        if isinstance(outcome, WaitingApproval):
            # The rest of the plan is not abandoned: it is dispatched again when
            # this step is re-queued, and its committed calls replay.
            return results, True
        results.append(await _result(context.session, run_id, proposed, outcome))
    return results, False


async def _result(
    session: AsyncSession,
    run_id: UUID,
    proposed: ProposedCall,
    outcome: Committed | Replayed | Denied,
) -> Json:
    """One call's tool result, and the mailbox notice a lost race also earns."""
    if isinstance(outcome, Committed):
        return {
            "tool_call_id": proposed.tool_call_id,
            "outcome": "committed",
            "result": outcome.result,
        }
    if isinstance(outcome, Replayed):
        return {
            "tool_call_id": proposed.tool_call_id,
            "outcome": "replayed",
            "action_id": str(outcome.action.id),
        }
    if outcome.reason == _CONFLICT:
        # The denial and this notice are the same transaction, so a run can never
        # be told about a conflict the ledger does not carry.
        await post(
            session,
            run_id,
            "conflict",
            {
                "text": f"{proposed.name} was refused: the record moved under it.",
                "expected": outcome.event.payload.get("expected"),
                "actual": outcome.event.payload.get("actual"),
                "tool_call_id": proposed.tool_call_id,
            },
        )
    return {
        "tool_call_id": proposed.tool_call_id,
        "outcome": "denied",
        "reason": outcome.reason,
    }


async def _expected_version(
    session: AsyncSession, registry: Registry, call: ProposedCall
) -> int | None:
    """ADR-0017: a versioned write states the version it read.

    Nothing hands the model one in Phase 1, so the step reads the aggregate's
    stream head as it dispatches; a step racing another writer then loses the
    check and gets the conflict denial, which is what that check is for.
    """
    try:
        op = registry.get(call.name)
    except KeyError:
        return None
    if op.aggregate is None:
        return None
    kind, path = op.aggregate
    try:
        target = UUID(str(call.args.get(path)))
    except ValueError:
        # A malformed id is dispatch's `invalid_args` to refuse, not ours to die on.
        return None
    head = await session.get(StreamHead, (UUID(session.info["org"]), kind, target))
    return head.version if head is not None else 0


async def _journal(
    session: AsyncSession, run_id: UUID, step_no: int, completion: Completion
) -> None:
    """The plan, before any of it runs.

    The model's own `tool_call_id`s go in it, because the reservation key is
    `sha256(run:step:tool_call_id)`: a worker that dies after this leaves a plan
    that names exactly the keys the next worker's dispatch will find taken.
    """
    await append(
        session,
        Append(
            kind="run_journal",
            aggregate_kind=AGGREGATE,
            aggregate_id=run_id,
            principal_id=UUID(session.info["principal"]),
            payload={
                "event": PLANNED,
                "text": completion.text,
                "calls": [
                    {
                        "name": call.name,
                        "args": call.args,
                        "tool_call_id": call.tool_call_id,
                    }
                    for call in completion.calls
                ],
            },
            run_id=run_id,
            step_no=step_no,
        ),
    )


async def _drain(
    session: AsyncSession, run_id: UUID
) -> tuple[int, Sequence[MailboxMessage]]:
    """D5: everything steered into the run since the last checkpoint, oldest first.

    The last checkpoint's `mailbox_seq` is the watermark, so a step worked again
    after a crash drains exactly what the crashed one drained, and a message can
    neither be read twice by two steps nor lost between them.
    """
    state = await session.scalar(
        select(Checkpoint.state)
        .where(Checkpoint.run_id == run_id)
        .order_by(Checkpoint.step_no.desc())
        .limit(1)
    )
    seen = state.get("mailbox_seq") if state else None
    after = seen if isinstance(seen, int) else 0
    rows = await session.scalars(
        select(MailboxMessage)
        .where(MailboxMessage.run_id == run_id, MailboxMessage.seq > after)
        .order_by(MailboxMessage.seq)
    )
    return after, rows.all()


def _intake(messages: Sequence[MailboxMessage]) -> str:
    """D5 and D6 as the one string assembly takes, until `surfaces` owns them.

    One tagged line per drained message, oldest first, so the model can tell a
    person's steer from the kernel's own conflict notice. An empty mailbox is an
    empty intake: the prefix already says what the run is.
    """
    lines: list[str] = []
    for message in messages:
        text = message.body.get("text")
        body = (
            text
            if isinstance(text, str)
            else json.dumps(message.body, sort_keys=True)
        )
        lines.append(f"[{message.kind}] {body}")
    return "\n\n".join(lines)
