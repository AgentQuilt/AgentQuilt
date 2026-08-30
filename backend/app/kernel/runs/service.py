"""What a person does to a run: start it, steer it, read it, cancel it.

Every function here runs inside the caller's transaction and reads the org and the
principal from the session, the way `declare.ledger` does: a caller cannot reach a
run it did not open the session with, and row-level security — not a `where` clause
written here — is what makes another org's run invisible.
"""

from __future__ import annotations

from collections.abc import Sequence
from uuid import UUID, uuid4

from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.kernel.declare.ledger import Append, append
from app.kernel.declare.models import Event
from app.kernel.declare.registry import Stage
from app.kernel.identity.models import Approval
from app.kernel.identity.service import effective_grants
from app.kernel.runs.models import MailboxMessage, StepQueue
from app.kernel.store.models import AgentDefinition, Json, Run, SkillVersion

# The run's aggregate in the ledger, and the two journal events this module writes.
AGGREGATE = "run"
CREATED = "run.created"
CANCELLED = "run.cancelled"
# A run starts at its first step, on the one queue Phase 1 has.
FIRST_STEP = 1
QUEUE_TAG = "main"
# Cancel closes what a person could still answer; the rest are already settled.
_ANSWERABLE = ("requested", "open")


async def create(
    session: AsyncSession,
    agent_definition: AgentDefinition,
    skill_version: SkillVersion | None,
    *,
    stage: Stage = "PROD",
) -> Run:
    """Start a run: ceiling computed once, first step queued, creation journaled."""
    # ADR-0012's one predicate, at run start: the build plane may bind anything,
    # a production run only what has been promoted to PROD.
    if stage == "PROD" and skill_version is not None and skill_version.stage != stage:
        raise ValueError(
            f"a PROD run cannot bind {skill_version.stage}-stage"
            f" skill version {skill_version.id}"
        )

    org = UUID(session.info["org"])
    principal = UUID(session.info["principal"])
    run = Run(
        id=uuid4(),
        org_id=org,
        agent_definition_id=agent_definition.id,
        skill_version_id=skill_version.id if skill_version is not None else None,
        stage=stage,
        state="queued",
        budget_cap_tokens=agent_definition.budget_cap_tokens,
        # The prefix key belongs to a turn, not to a run: assembly computes it per
        # step and records it on `context_manifest`. The run carries the latest.
        prefix_key="",
        # ADR-0015's ceiling: the most this run may ever do, fixed here and
        # never widened. Phase 1 has no dossier ACLs, no counterparty tier and
        # no task purpose, so the intersection is the originator's grants with
        # the definition's memory scope.
        capability_ceiling={
            "operations": dict(await effective_grants(session, principal)),
            "memory_scope": agent_definition.memory_scope,
        },
        prefix_profile="personal",
    )
    session.add(run)
    # No relationships are mapped, so the unit of work has no dependency graph:
    # the run flushes first or its queue row has nothing to point at.
    await session.flush()
    session.add(
        StepQueue(
            org_id=org, run_id=run.id, step_no=FIRST_STEP, queue_tag=QUEUE_TAG
        )
    )
    # The queue row has to land as the app role: `append` switches the connection
    # to `agentquilt_ledger_writer`, which owns nothing in `core`.
    await session.flush()
    await append(
        session,
        Append(
            kind="run_journal",
            aggregate_kind=AGGREGATE,
            aggregate_id=run.id,
            principal_id=principal,
            payload={"event": CREATED, "stage": stage, "state": run.state},
            run_id=run.id,
            step_no=FIRST_STEP,
        ),
    )
    return run


async def send(
    session: AsyncSession, run_id: UUID, text: str
) -> MailboxMessage | None:
    """Steer a live run, or None when this org has no such run."""
    return await post(session, run_id, "steer", {"text": text})


async def post(
    session: AsyncSession, run_id: UUID, kind: str, body: Json
) -> MailboxMessage | None:
    """One message into a run's mailbox, or None when this org has no such run.

    The lock on the run row is what serialises `seq`: a second writer reads the
    first's message only after it lands, so the numbers cannot collide or gap.
    The worker posts the kernel's own `conflict` notices through here, so there
    is one allocator and not two.
    """
    locked = await session.scalar(
        select(Run.id).where(Run.id == run_id).with_for_update()
    )
    if locked is None:
        return None
    seq = await session.scalar(
        select(func.coalesce(func.max(MailboxMessage.seq), 0) + 1).where(
            MailboxMessage.run_id == run_id
        )
    )
    message = MailboxMessage(
        id=uuid4(),
        org_id=UUID(session.info["org"]),
        run_id=run_id,
        seq=seq,
        kind=kind,
        author_principal_id=UUID(session.info["principal"]),
        body=body,
    )
    session.add(message)
    await session.flush()
    return message


async def events(
    session: AsyncSession, run_id: UUID, after_cursor: int = 0
) -> Sequence[Event]:
    """The run's ledger stream in order. The cursor is the last `Event.id` read."""
    rows = await session.scalars(
        select(Event)
        .where(Event.run_id == run_id, Event.id > after_cursor)
        .order_by(Event.id)
    )
    return rows.all()


async def cancel(session: AsyncSession, run_id: UUID) -> bool:
    """Stop a run for good: state, queue, open approvals and journal, together."""
    cancelled = await session.scalar(
        update(Run)
        .where(Run.id == run_id)
        .values(state="cancelled", updated_at=func.now())
        .returning(Run.id)
        .execution_options(synchronize_session=False)
    )
    if cancelled is None:
        return False
    await session.execute(delete(StepQueue).where(StepQueue.run_id == run_id))
    await session.execute(
        update(Approval)
        .where(Approval.run_id == run_id, Approval.state.in_(_ANSWERABLE))
        .values(state="expired")
        .execution_options(synchronize_session=False)
    )
    await append(
        session,
        Append(
            kind="run_journal",
            aggregate_kind=AGGREGATE,
            aggregate_id=run_id,
            principal_id=UUID(session.info["principal"]),
            payload={"event": CANCELLED},
            run_id=run_id,
            step_no=None,
        ),
    )
    return True
