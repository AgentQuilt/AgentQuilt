"""Skills: what a run may bind, and how a version reaches a stage.

The two tables stay mapped in `kernel/store/models` because `core.run` carries a
foreign key to `mod_skills.skill_version` and the kernel reads both (the `skills`
context contributor and `runs.create`); this module owns what is done with them.

Activation is one declared operation and is its own compensator: the action
records the stage it replaced, so undoing it is the same call with that stage
(ADR-0003's reversible class, the compensator contract in `declare/service`).
"""

from __future__ import annotations

from dataclasses import dataclass

from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.kernel.declare.models import Json
from app.kernel.declare.registry import CallContext, Declares, Stage, registry
from app.kernel.store.models import Skill, SkillVersion

ACTIVATE = "skills.activate_version"
# ADR-0013: an inline skill is judgment only. It folds into the running agent's
# context and uses the tools that agent already has, so a body that also claims
# operations would rewrite the tool block the prefix is cached on.
INLINE = "inline"


@dataclass(frozen=True, slots=True)
class Bindable:
    """One skill version a run at this stage may bind (ADR-0012)."""

    name: str
    version_id: str
    execution_mode: str


class ActivateVersion(BaseModel):
    skill_version_id: str
    stage: Stage


async def directory(
    session: AsyncSession, *, stage: Stage = "PROD"
) -> tuple[Bindable, ...]:
    """Every skill version promoted to this stage, by skill name."""
    rows = await session.execute(
        select(Skill.name, SkillVersion.id, SkillVersion.execution_mode)
        .join(SkillVersion, SkillVersion.skill_id == Skill.id)
        .where(SkillVersion.stage == stage)
        .order_by(Skill.name, SkillVersion.id)
    )
    return tuple(Bindable(*row) for row in rows)


async def activate(
    session: AsyncSession, skill_version_id: str, stage: Stage
) -> str:
    """Move one version to a stage and return the stage it left.

    The returned stage is what makes activation reversible: the action's
    compensator arguments are this result, so replaying the call restores it.
    """
    version = await session.get_one(SkillVersion, skill_version_id)
    if version.execution_mode == INLINE and version.operations:
        raise ValueError(
            f"skill version {version.id} is inline and declares"
            f" {sorted(version.operations)}; an inline skill declares no"
            " operations (ADR-0013)"
        )
    previous, version.stage = version.stage, stage
    await session.flush()
    return previous


# PROD, unlike the governance operations a person calls from outside a run: this
# is the operation an agent proposes, so it has to be in the run's L5 tool block.
@registry.operation(
    ACTIVATE,
    Declares(
        mode="write", reversal="reversible", compensator=ACTIVATE, stage="PROD"
    ),
)
async def activate_version(ctx: CallContext, args: ActivateVersion) -> Json:
    """Promote one skill version to a stage; undoing it restores the old one."""
    previous = await activate(ctx.session, args.skill_version_id, args.stage)
    return {"skill_version_id": args.skill_version_id, "stage": previous}
