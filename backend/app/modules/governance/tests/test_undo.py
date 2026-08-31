"""Undo, through dispatch, against a real Postgres: what is undoable and what is not.

Both tests go through `dispatch` rather than calling the operation, because what
is under test is the pair the ledger records — the action a call leaves behind,
and the reversal that reads it back — and only dispatch writes either.
"""

from __future__ import annotations

from uuid import UUID, uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.kernel.declare.registry import CallContext, registry
from app.kernel.declare.service import Call, Committed, dispatch
from app.kernel.runs.models import MailboxMessage, StepQueue
from app.kernel.store.models import Principal, Run, Skill, SkillVersion
from app.kernel.store.service import session
from app.modules.governance.service import NAME as DECIDE, UNDO
from app.modules.skills.service import ACTIVATE
from tests.kit import Scope, two_principals
from tests.kit_notes import grant

pytestmark = pytest.mark.anyio


@pytest.fixture(scope="module")
async def person(migrated_url: str) -> Scope:
    """The org, acting as its user: a person is who undoes an action."""
    first, _ = await two_principals(migrated_url)
    async with session(*first) as scoped:
        principal_id = (
            await scoped.scalars(
                select(Principal.id).where(Principal.class_ == "user")
            )
        ).one()
        await registry.publish(scoped)
        for name in (ACTIVATE, DECIDE, UNDO):
            await grant(scoped, principal_id, name, "may_use")
        await scoped.commit()
    return first[0], principal_id


def _ctx(scoped: AsyncSession, principal_id: UUID) -> CallContext:
    """A person's call: outside any run, so it carries no ceiling and no step."""
    return CallContext(
        session=scoped,
        principal_id=principal_id,
        run_id=None,
        step_no=None,
        registry=registry,
    )


async def _committed(
    scoped: AsyncSession, principal_id: UUID, call: Call
) -> Committed:
    outcome = await dispatch(_ctx(scoped, principal_id), call)
    assert isinstance(outcome, Committed)
    assert outcome.action is not None
    return outcome


async def _skill_version(scoped: AsyncSession, org_id: UUID) -> str:
    skill_id, version_id = uuid4(), str(uuid4())
    scoped.add(Skill(id=skill_id, org_id=org_id, name=f"skill {skill_id}"))
    await scoped.flush()
    scoped.add(
        SkillVersion(
            id=version_id,
            org_id=org_id,
            skill_id=skill_id,
            tier="executor",
            execution_mode="inline",
            operations={},
            stage="DEV",
            body="Answer from the notes.",
        )
    )
    await scoped.flush()
    return version_id


async def test_action_written_and_undoable(person: Scope) -> None:
    """A reversible call records what undoing it needs, and undo queues that run."""
    org_id, principal_id = person
    async with session(org_id, principal_id) as scoped:
        version_id = await _skill_version(scoped, org_id)
        activated = await _committed(
            scoped,
            principal_id,
            Call(
                operation_name=ACTIVATE,
                args={"skill_version_id": version_id, "stage": "PROD"},
                tool_call_id="activate-1",
            ),
        )
        # The action carries the reversal: the compensator, and the stage the
        # version left, which is what running it again restores.
        assert activated.action is not None
        assert activated.action.compensator_ref == ACTIVATE
        assert activated.action.compensator_args == {
            "skill_version_id": version_id,
            "stage": "DEV",
        }

        undone = await _committed(
            scoped,
            principal_id,
            Call(
                operation_name=UNDO,
                args={"action_id": str(activated.action.id)},
                tool_call_id="undo-1",
            ),
        )
        await scoped.commit()

    assert undone.result["compensator"] == ACTIVATE
    compensating = UUID(str(undone.result["undo_run_id"]))
    async with session(org_id, principal_id) as scoped:
        run = await scoped.get_one(Run, compensating)
        queued = await scoped.scalars(
            select(StepQueue.step_no).where(StepQueue.run_id == compensating)
        )
        steer = (
            await scoped.scalars(
                select(MailboxMessage).where(MailboxMessage.run_id == compensating)
            )
        ).one()
    # The compensator is not run here: it is a queued step for the worker, with
    # the recorded arguments in the message it will read.
    assert run.state == "queued"
    assert queued.all() == [1]
    assert steer.kind == "steer"
    assert ACTIVATE in str(steer.body["text"])
    assert '"stage": "DEV"' in str(steer.body["text"])


async def test_irreversible_undo_refused_with_reason(person: Scope) -> None:
    """An operation that names no compensator says so, and nothing is queued."""
    org_id, principal_id = person
    async with session(org_id, principal_id) as scoped:
        decided = await _committed(
            scoped,
            principal_id,
            Call(
                operation_name=DECIDE,
                args={"decision": "approve", "approval_id": str(uuid4())},
                tool_call_id="decide-1",
            ),
        )
        assert decided.action is not None
        runs_before = len((await scoped.scalars(select(Run.id))).all())
        refused = await _committed(
            scoped,
            principal_id,
            Call(
                operation_name=UNDO,
                args={"action_id": str(decided.action.id)},
                tool_call_id="undo-2",
            ),
        )
        runs_after = len((await scoped.scalars(select(Run.id))).all())
        await scoped.commit()

    assert refused.result["undo_run_id"] is None
    assert (
        refused.result["reason"]
        == f"{DECIDE} is irreversible: it declares no compensator"
    )
    assert runs_after == runs_before
