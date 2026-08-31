"""Two orgs with a user, a token and an agent definition each (D6), and the
tier binding they run under.

Every insert goes through the scoped session rather than a superuser connection,
so a seed run that succeeds is evidence the RLS write path works.
"""

from __future__ import annotations

import hashlib
import secrets
from dataclasses import dataclass
from uuid import UUID, uuid4

from sqlalchemy.dialects.postgresql import insert

from app.kernel.identity.models import Grant
from app.kernel.model.models import TierBinding
from app.kernel.store.models import AgentDefinition, Org, Principal, User, UserToken
from app.kernel.store.service import session

ORG_NAMES = ("Org A", "Org B")
# The migration fixes the four tier names; what a tier resolves to is data, and
# this is the deployment's first row of it. Deployment-global, so it carries a
# fixed id and a second seed run leaves the row alone.
EXECUTOR_BINDING = {
    "id": UUID("f1a4d8be-6d1f-4a3e-9c2b-0a5f7c3e1b00"),
    "tier": "executor",
    "provider": "openrouter",
    "model": "z-ai/glm-5.3-flash",
    "effort": None,
    "version": 1,
}
# The one operation the seeded agent may propose, and so the one action a person
# can undo. Written as a string rather than imported, because `store` is kernel
# and `skills.activate_version` is a buildable module's declaration.
UNDOABLE_OPERATION = "skills.activate_version"
SOUL_TEXT = (
    "You are the assistant of this organization.\n"
    "You answer from what the organization knows, and you say when it does not."
)


@dataclass(frozen=True, slots=True)
class SeededOrg:
    org_id: UUID
    system_principal_id: UUID
    user_id: UUID
    token: str


async def seed() -> list[SeededOrg]:
    seeded: list[SeededOrg] = []
    for name in ORG_NAMES:
        org_id, system_principal_id = uuid4(), uuid4()
        user_principal_id, user_id = uuid4(), uuid4()
        token = secrets.token_urlsafe(32)
        async with session(org_id, system_principal_id) as scoped:
            # No relationships are mapped, so the unit of work has no dependency
            # graph and orders inserts by mapper name: the parents flush first.
            scoped.add(Org(id=org_id, name=name))
            await scoped.flush()
            scoped.add(User(id=user_id, org_id=org_id, display_name=f"{name} owner"))
            await scoped.flush()
            scoped.add(
                Principal(id=system_principal_id, org_id=org_id, class_="system")
            )
            scoped.add(
                Principal(
                    id=user_principal_id,
                    org_id=org_id,
                    class_="user",
                    user_id=user_id,
                )
            )
            scoped.add(
                UserToken(
                    id=uuid4(),
                    user_id=user_id,
                    org_id=org_id,
                    token_hash=hashlib.sha256(token.encode()).hexdigest(),
                )
            )
            scoped.add(
                AgentDefinition(
                    id=uuid4(),
                    org_id=org_id,
                    name="assistant",
                    version=1,
                    soul_text=SOUL_TEXT,
                    tier="executor",
                    budget_cap_tokens=200_000,
                    memory_scope="org",
                )
            )
            # After the principals: mapper name orders this batch's inserts, and
            # the grants point at two of them.
            await scoped.flush()
            # Both principals, because `runs.create` fixes a run's ceiling from
            # the grants of whoever creates it: the agent proposes the
            # operation, and a run the person starts (the web thread, or the one
            # undo starts) would otherwise carry a ceiling without it.
            for principal_id in (system_principal_id, user_principal_id):
                scoped.add(
                    Grant(
                        id=uuid4(),
                        org_id=org_id,
                        principal_id=principal_id,
                        operation_name=UNDOABLE_OPERATION,
                        level="asks_first",
                    )
                )
            await scoped.commit()
        seeded.append(SeededOrg(org_id, system_principal_id, user_id, token))
    await _bind_executor_tier(seeded[0])
    return seeded


async def _bind_executor_tier(org: SeededOrg) -> None:
    """`core.tier_binding` is global, and a session is always org-scoped: the
    first seeded org opens the one this row is written through."""
    async with session(org.org_id, org.system_principal_id) as scoped:
        await scoped.execute(
            insert(TierBinding)
            .values(EXECUTOR_BINDING)
            .on_conflict_do_nothing(index_elements=[TierBinding.id])
        )
        await scoped.commit()
