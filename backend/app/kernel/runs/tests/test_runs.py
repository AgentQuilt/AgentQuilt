"""Starting, steering, reading and cancelling a run, against a real Postgres.

The mailbox test is two real sessions on two connections, because the thing under
test is a row lock; and org B's steer is refused by row-level security, not by a
`where` clause, so the proof is that the same call from the other org finds nothing.
"""

from __future__ import annotations

import asyncio
from uuid import UUID, uuid4

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.kernel.declare.models import OperationVersion
from app.kernel.identity.models import Approval
from app.kernel.runs.models import MailboxMessage, StepQueue
from app.kernel.runs.service import (
    CANCELLED,
    CREATED,
    QUEUE_TAG,
    cancel,
    create,
    events,
    send,
)
from app.kernel.store.models import AgentDefinition, Run, Skill, SkillVersion
from app.kernel.store.service import session
from tests.kit import START, Scope, two_principals
from tests.kit_notes import grant

pytestmark = pytest.mark.anyio

WRITE = "note.write_note"
# This module's own operation version, so publishing it cannot collide with the
# ids another test module's registry publishes into the same global table.
VERSION = "note.write_note@runs-test"


@pytest.fixture(scope="module")
async def scopes(migrated_url: str) -> tuple[Scope, Scope]:
    return await two_principals(migrated_url)


async def _definition(scoped: AsyncSession) -> AgentDefinition:
    """The agent definition `seed` wrote for this org."""
    definition = await scoped.scalar(select(AgentDefinition).limit(1))
    assert definition is not None
    return definition


async def _run(scope: Scope) -> UUID:
    async with session(*scope) as scoped:
        run = await create(scoped, await _definition(scoped), None)
        await scoped.commit()
        return run.id


async def _steer(scope: Scope, run_id: UUID, text: str) -> None:
    async with session(*scope) as scoped:
        await send(scoped, run_id, text)
        await scoped.commit()


async def test_user_creates_run(scopes: tuple[Scope, Scope]) -> None:
    scope = scopes[0]
    async with session(*scope) as scoped:
        await grant(scoped, scope[1], WRITE, "may_use")
        definition = await _definition(scoped)
        run = await create(scoped, definition, None)
        await scoped.commit()

    assert run.capability_ceiling == {
        "operations": {WRITE: "may_use"},
        "memory_scope": definition.memory_scope,
    }
    async with session(*scope) as scoped:
        queued = await scoped.scalar(
            select(StepQueue.queue_tag).where(StepQueue.run_id == run.id)
        )
        stream = await events(scoped, run.id)
    assert queued == QUEUE_TAG
    assert [one.kind for one in stream] == ["run_journal"]
    assert [one.payload["event"] for one in stream] == [CREATED]


async def test_prod_run_refuses_a_dev_skill_version(
    scopes: tuple[Scope, Scope],
) -> None:
    scope = scopes[0]
    async with session(*scope) as scoped:
        skill_id = uuid4()
        scoped.add(Skill(id=skill_id, org_id=scope[0], name="triage"))
        await scoped.flush()
        version = SkillVersion(
            id="triage@1",
            org_id=scope[0],
            skill_id=skill_id,
            tier="executor",
            execution_mode="inline",
            operations={},
            stage="DEV",
            body="",
        )
        scoped.add(version)
        await scoped.flush()
        definition = await _definition(scoped)

        with pytest.raises(ValueError, match="PROD run"):
            await create(scoped, definition, version)
        built = await create(scoped, definition, version, stage="DEV")
        await scoped.commit()
    assert built.skill_version_id == version.id


async def test_mailbox_seq_serialises_two_senders(
    scopes: tuple[Scope, Scope],
) -> None:
    scope = scopes[0]
    run_id = await _run(scope)
    await asyncio.gather(
        _steer(scope, run_id, "first"), _steer(scope, run_id, "second")
    )
    async with session(*scope) as scoped:
        rows = (
            await scoped.execute(
                select(MailboxMessage.seq, MailboxMessage.author_principal_id)
                .where(MailboxMessage.run_id == run_id)
                .order_by(MailboxMessage.seq)
            )
        ).all()
    assert [seq for seq, _ in rows] == [1, 2]
    assert {author for _, author in rows} == {scope[1]}


async def test_org_b_cannot_steer(scopes: tuple[Scope, Scope]) -> None:
    run_id = await _run(scopes[0])
    async with session(*scopes[1]) as scoped:
        assert await send(scoped, run_id, "theirs") is None
        await scoped.commit()
    async with session(*scopes[0]) as scoped:
        written = await scoped.scalar(
            select(func.count())
            .select_from(MailboxMessage)
            .where(MailboxMessage.run_id == run_id)
        )
    assert written == 0


async def test_cancel_clears_queue_and_open_approvals(
    scopes: tuple[Scope, Scope],
) -> None:
    scope = scopes[0]
    run_id = await _run(scope)
    approval_id = uuid4()
    async with session(*scope) as scoped:
        scoped.add(
            OperationVersion(
                id=VERSION, operation_name=WRITE, stage="DEV", declaration={}
            )
        )
        await scoped.flush()
        scoped.add(
            Approval(
                id=approval_id,
                org_id=scope[0],
                granted_to=scope[1],
                operation_version_id=VERSION,
                args_hash="",
                state="requested",
                run_id=run_id,
                step_no=1,
                tool_call_id="call-1",
                expires_at=START,
            )
        )
        await scoped.commit()

    async with session(*scope) as scoped:
        assert await cancel(scoped, run_id) is True
        await scoped.commit()

    async with session(*scope) as scoped:
        run = await scoped.get(Run, run_id)
        approval = await scoped.get(Approval, approval_id)
        queued = await scoped.scalar(
            select(func.count())
            .select_from(StepQueue)
            .where(StepQueue.run_id == run_id)
        )
        stream = await events(scoped, run_id)
    assert run is not None and run.state == "cancelled"
    assert approval is not None and approval.state == "expired"
    assert queued == 0
    assert [one.payload["event"] for one in stream] == [CREATED, CANCELLED]
