"""The directory a run binds from, and the rule an inline skill cannot break.

Against a real Postgres at head, through the module's own interface: what a run
carries afterwards is one skill version id, and what `activate` refuses is the
first negative fixture ADR-0013 asks for.
"""

from __future__ import annotations

from uuid import UUID, uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.kernel.runs.service import create
from app.kernel.store.models import AgentDefinition, Skill, SkillVersion
from app.kernel.store.service import session
from app.modules.skills.service import activate, directory
from tests.kit import Scope, two_principals

pytestmark = pytest.mark.anyio

BODY = "Read the note, then answer in one paragraph."


@pytest.fixture(scope="module")
async def scope(migrated_url: str) -> Scope:
    first, _ = await two_principals(migrated_url)
    return first


async def _version(
    scoped: AsyncSession, org_id: UUID, mode: str, operations: dict[str, object]
) -> SkillVersion:
    """One skill and one DEV version of it, ready to be activated."""
    skill_id = uuid4()
    scoped.add(Skill(id=skill_id, org_id=org_id, name=f"skill {skill_id}"))
    await scoped.flush()
    version = SkillVersion(
        id=str(uuid4()),
        org_id=org_id,
        skill_id=skill_id,
        tier="executor",
        execution_mode=mode,
        operations=operations,
        stage="DEV",
        body=BODY,
    )
    scoped.add(version)
    await scoped.flush()
    return version


async def test_run_binds_one_skill_version(scope: Scope) -> None:
    """The directory is what a PROD run may bind, and a run binds one of it."""
    async with session(*scope) as scoped:
        promoted = await _version(scoped, scope[0], "inline", {})
        held_back = await _version(scoped, scope[0], "inline", {})
        assert await activate(scoped, promoted.id, "PROD") == "DEV"

        bindable = await directory(scoped)
        assert promoted.id in [one.version_id for one in bindable]
        assert held_back.id not in [one.version_id for one in bindable]

        definition = (await scoped.scalars(select(AgentDefinition).limit(1))).one()
        run = await create(scoped, definition, promoted)
        await scoped.commit()
    assert run.skill_version_id == promoted.id


async def test_inline_skill_with_operations_rejected(scope: Scope) -> None:
    """ADR-0013: an inline skill is judgment only and declares no operations."""
    async with session(*scope) as scoped:
        delegated = await _version(
            scoped, scope[0], "delegated", {"note.write_note": {}}
        )
        # The same operations block is the difference: delegated may declare it.
        assert await activate(scoped, delegated.id, "PROD") == "DEV"

        inline = await _version(scoped, scope[0], "inline", {"note.write_note": {}})
        with pytest.raises(ValueError, match="inline skill declares no operations"):
            await activate(scoped, inline.id, "PROD")
        await scoped.rollback()
