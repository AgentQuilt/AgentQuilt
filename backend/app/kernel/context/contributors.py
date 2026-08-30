"""The two Phase 1 contributors, behind `ports/context_contributor`.

`instructions` renders the three text layers from what the spine already stores;
`skills` is one object satisfying both contracts, because the same module owns the
directory in the prefix and the bound body in the envelope. Neither knows the slot
order, the tool block or the key: those are `service`'s.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.kernel.ports.context_contributor import (
    EnvelopeSlot,
    Layer,
    PrefixProfile,
    PrefixSlot,
    Scope,
    Slice,
    Turn,
)
from app.kernel.store.models import (
    AgentDefinition,
    Org,
    Principal,
    Run,
    Skill,
    SkillVersion,
    User,
)


def version(term: str, body: str) -> str:
    """A layer's term in `prefix_key`: what the layer is, and the bytes it rendered.

    The digest is what makes the key change whenever the body changes (ADR-0014);
    the term in front of it is there so a key that differs can be read by eye.
    """
    return f"{term}:{hashlib.sha256(body.encode()).hexdigest()[:16]}"


@dataclass(frozen=True, slots=True)
class Instructions:
    """What L1, L2 and L3 render from: one fetch's rows, no session behind them."""

    org_name: str
    agent_name: str
    agent_version: int
    soul_text: str
    profile: str
    prefix_profile: PrefixProfile
    principal_id: UUID


class InstructionsContributor:
    """L1 the org's text, L2 the agent's soul, L3 the personal profile (ADR-0016).

    Phase 1 stores neither org-instruction text nor a curated profile, so L1
    renders from `core.org.name` and L3 from the acting principal's
    `core.user.display_name`. The slots, their order and their versions do not
    change when a real store lands behind either.
    """

    owner = "instructions"
    prefix_slots: tuple[PrefixSlot, ...] = ("L1", "L2", "L3")

    async def fetch(self, session: AsyncSession, scope: Scope) -> Instructions:
        # The session is scoped to one org, so `core.org` holds exactly one row.
        org_name = await session.scalar(select(Org.name))
        agent = (
            await session.execute(
                select(
                    AgentDefinition.name,
                    AgentDefinition.version,
                    AgentDefinition.soul_text,
                ).where(AgentDefinition.id == scope.agent_definition_id)
            )
        ).one()
        profile = await session.scalar(
            select(User.display_name)
            .join(Principal, Principal.user_id == User.id)
            .where(Principal.id == scope.principal_id)
        )
        return Instructions(
            org_name=org_name or "",
            agent_name=agent.name,
            agent_version=agent.version,
            soul_text=agent.soul_text,
            profile=profile or "",
            prefix_profile=scope.prefix_profile,
            principal_id=scope.principal_id,
        )

    def layers(self, source: Instructions) -> tuple[Layer, ...]:
        org = f"You are working for {source.org_name}."
        agent = f"{source.agent_name}@{source.agent_version}"
        return (
            Layer(slot="L1", version=version("org", org), body=org),
            Layer(
                slot="L2",
                version=version(agent, source.soul_text),
                body=source.soul_text,
            ),
            self._personal(source),
        )

    def _personal(self, source: Instructions) -> Layer:
        """L3. Under `none` the version is the profile term and the body is empty
        (ADR-0016); `space` renders the same way until a space's own instructions
        have somewhere to be stored."""
        if source.prefix_profile != "personal":
            return Layer(slot="L3", version=source.prefix_profile, body="")
        body = f"The person you are working with is {source.profile}."
        return Layer(
            slot="L3",
            version=version(f"personal:{source.principal_id}", body),
            body=body,
        )


class SkillsContributor:
    """L6 the skill directory, D1 the body of the version this run is bound to."""

    owner = "skills"
    prefix_slots: tuple[PrefixSlot, ...] = ("L6",)
    envelope_slots: tuple[EnvelopeSlot, ...] = ("D1",)

    async def fetch(self, session: AsyncSession, scope: Scope) -> tuple[str, ...]:
        names = await session.scalars(select(Skill.name).order_by(Skill.name))
        return tuple(names)

    def layers(self, source: tuple[str, ...]) -> tuple[Layer, ...]:
        body = "\n".join(source)
        return (Layer(slot="L6", version=version("skills", body), body=body),)

    async def slices(
        self, session: AsyncSession, scope: Scope, turn: Turn
    ) -> tuple[Slice, ...]:
        bound = (
            await session.execute(
                select(SkillVersion.id, SkillVersion.body)
                .join(Run, Run.skill_version_id == SkillVersion.id)
                .where(Run.id == turn.run_id)
            )
        ).first()
        if bound is None:
            return ()
        # A skill body is droppable before the person's own message is.
        return (Slice(slot="D1", body=bound.body, provenance=bound.id, priority=1),)
