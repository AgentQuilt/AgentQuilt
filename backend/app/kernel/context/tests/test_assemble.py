"""Assembly against a real Postgres: the key, the manifest row and the budget.

The prefix key is the cache key (ADR-0014), so the two properties that matter are
that it holds across turns and moves when a layer does; the manifest is what makes
a past prompt readable, so a call that writes none is a call that cannot be
debugged.
"""

from __future__ import annotations

import importlib
from dataclasses import dataclass, replace
from uuid import UUID, uuid4

import pytest
from pydantic import BaseModel
from sqlalchemy import func, select, update

from app.kernel.context import service
from app.kernel.context.models import ContextManifest
from app.kernel.context.service import AssembledTurn, Call, assemble, tokens
from app.kernel.declare.models import Json
from app.kernel.declare.registry import CallContext, Declares, Registry
from app.kernel.identity.models import Grant
from app.kernel.model.models import TierBinding
from app.kernel.ports.context_contributor import Layer
from app.kernel.store.models import AgentDefinition, Principal, Run, Skill, SkillVersion
from app.kernel.store.service import session
from tests.kit import StaticContributor, two_principals

pytestmark = pytest.mark.anyio

SKILL_BODY = "Read the note, then answer in one paragraph."
CALL = Call(
    budget_tokens=200_000,
    intake="Where did we land on the pricing note?",
)


class Args(BaseModel):
    body: str


async def _write_note(ctx: CallContext, args: Args) -> Json:
    """Write a note."""
    return {"body": args.body}


async def _get_note(ctx: CallContext, args: Args) -> Json:
    """Read a note."""
    return {"body": args.body}


def _registry() -> Registry:
    """Two PROD operations, one of which the run's ceiling allows."""
    registry = Registry()
    registry.operation(
        "note.write_note",
        Declares(mode="write", reversal="irreversible", stage="PROD"),
    )(_write_note)
    registry.operation("note.get_note", Declares(mode="read", stage="PROD"))(_get_note)
    return registry


@dataclass(frozen=True, slots=True)
class Setup:
    org_id: UUID
    principal_id: UUID
    run: Run


@pytest.fixture(scope="module")
async def setup(migrated_url: str) -> Setup:
    """One org, its user principal, one skill bound to one run.

    `app.modules` is imported for its side effect: L4 is `modules/surfaces`'
    since the owner's D2 fell due, so a full prefix needs the modules loaded.
    """
    importlib.import_module("app.modules")
    (org_id, system_id), _ = await two_principals(migrated_url)
    async with session(org_id, system_id) as scoped:
        agent_id = (await scoped.scalars(select(AgentDefinition.id))).one()
        principal_id = (
            await scoped.scalars(
                select(Principal.id).where(Principal.class_ == "user")
            )
        ).one()
        skill_id, skill_version_id = uuid4(), "skill-version-1"
        scoped.add(Skill(id=skill_id, org_id=org_id, name="answer from notes"))
        await scoped.flush()
        scoped.add(
            SkillVersion(
                id=skill_version_id,
                org_id=org_id,
                skill_id=skill_id,
                tier="executor",
                execution_mode="inline",
                operations={},
                stage="DEV",
                body=SKILL_BODY,
            )
        )
        scoped.add(
            Grant(
                id=uuid4(),
                org_id=org_id,
                principal_id=principal_id,
                operation_name="note.write_note",
                level="may_use",
                scope_ref=None,
            )
        )
        await scoped.flush()
        run = Run(
            id=uuid4(),
            org_id=org_id,
            agent_definition_id=agent_id,
            skill_version_id=skill_version_id,
            stage="DEV",
            state="running",
            budget_cap_tokens=200_000,
            prefix_key="",
            # ADR-0015: what L5 renders is this, not the acting principal's grants.
            capability_ceiling={"operations": {"note.write_note": "may_use"}},
            prefix_profile="personal",
        )
        scoped.add(run)
        await scoped.commit()
    return Setup(org_id=org_id, principal_id=principal_id, run=run)


async def _assemble(setup: Setup, step_no: int, call: Call = CALL) -> AssembledTurn:
    async with session(setup.org_id, setup.principal_id) as scoped:
        assembled = await assemble(
            scoped, setup.run, step_no, call=call, registry=_registry()
        )
        await scoped.commit()
    return assembled


async def test_prefix_key_stable_across_turns(setup: Setup) -> None:
    first = await _assemble(setup, 1)
    second = await _assemble(setup, 2, replace(CALL, intake="And the timeline?"))
    assert first.prefix_key == second.prefix_key
    assert [layer.slot for layer in first.prefix] == [
        "L0",
        "L1",
        "L2",
        "L3",
        "L4",
        "L5",
        "L6",
    ]
    # L4 is in the list only because importing `app.modules` registered its
    # contributor: the slot is the module's, not the kernel's.
    assert next(one.owner for one in first.prefix if one.slot == "L4") == "surfaces"


async def test_manifest_persisted_per_call(setup: Setup) -> None:
    rows = select(func.count()).select_from(ContextManifest)
    async with session(setup.org_id, setup.principal_id) as scoped:
        before = (await scoped.scalars(rows)).one()
    assembled = await _assemble(setup, 3)
    async with session(setup.org_id, setup.principal_id) as scoped:
        after = (await scoped.scalars(rows)).one()
        manifest = await scoped.get_one(ContextManifest, assembled.manifest_id)
    assert after == before + 1
    assert manifest.prefix_key == assembled.prefix_key
    assert manifest.token_cost == assembled.token_cost
    assert manifest.effective_scope["grants"] == {"note.write_note": "may_use"}


async def test_tool_block_carries_only_the_ceiling(setup: Setup) -> None:
    """The core tool set is the run's ceiling, fixed for the life of the prefix."""
    assembled = await _assemble(setup, 4)
    tools = next(layer for layer in assembled.prefix if layer.slot == "L5")
    assert "note.write_note" in tools.body
    assert "note.get_note" not in tools.body


async def test_over_budget_drops_the_lowest_priority_slice(setup: Setup) -> None:
    generous = await _assemble(setup, 5)
    tight = await _assemble(
        setup,
        6,
        replace(CALL, budget_tokens=generous.token_cost - tokens(SKILL_BODY)),
    )
    assert [kept.slot for kept in generous.envelope] == ["D1", "D6"]
    # D1, the skill body, declares the higher number, so it goes and the person's
    # own message stays.
    assert [kept.slot for kept in tight.envelope] == ["D6"]


async def test_prefix_key_changes_with_layer_version(setup: Setup) -> None:
    before = await _assemble(setup, 7)
    async with session(setup.org_id, setup.principal_id) as scoped:
        await scoped.execute(
            update(AgentDefinition)
            .where(AgentDefinition.id == setup.run.agent_definition_id)
            .values(soul_text="You answer only from the notes you were given.")
        )
        await scoped.commit()
    assert (await _assemble(setup, 8)).prefix_key != before.prefix_key


async def test_prefix_key_changes_with_tier_binding(setup: Setup) -> None:
    """The binding is a term of the key (ADR-0014), read where the key is made."""
    before = await _assemble(setup, 9)
    rebind = update(TierBinding).values(model="z-ai/glm-5.3")
    restore = update(TierBinding).values(model=before.binding.model)
    async with session(setup.org_id, setup.principal_id) as scoped:
        await scoped.execute(rebind)
        await scoped.commit()
    rebound = await _assemble(setup, 10)
    async with session(setup.org_id, setup.principal_id) as scoped:
        await scoped.execute(restore)
        await scoped.commit()
    assert rebound.prefix_key != before.prefix_key
    assert rebound.binding.model == "z-ai/glm-5.3"


async def test_colliding_contributor_is_rejected(
    setup: Setup, monkeypatch: pytest.MonkeyPatch
) -> None:
    """ADR-0027: a slot another contributor owns is refused, not shadowed."""
    rogue = StaticContributor(
        "rogue", (Layer(slot="L1", version="v1", body="mine now"),), ()
    )
    monkeypatch.setattr(
        service, "PREFIX_CONTRIBUTORS", (*service.PREFIX_CONTRIBUTORS, rogue)
    )
    with pytest.raises(ValueError, match="owned by 'instructions'"):
        await _assemble(setup, 11)


async def test_undeclared_slot_is_rejected(
    setup: Setup, monkeypatch: pytest.MonkeyPatch
) -> None:
    rogue = StaticContributor(
        "rogue", (Layer(slot="L1", version="v1", body="mine now"),), ()
    )
    rogue.prefix_slots = ("L6",)
    monkeypatch.setattr(
        service, "PREFIX_CONTRIBUTORS", (*service.PREFIX_CONTRIBUTORS, rogue)
    )
    with pytest.raises(ValueError, match="never declared"):
        await _assemble(setup, 12)
