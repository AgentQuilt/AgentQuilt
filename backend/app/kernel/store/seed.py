"""Two orgs with a user, a token and an agent definition each (D6).

Every insert goes through the scoped session rather than a superuser connection,
so a seed run that succeeds is evidence the RLS write path works.
"""

from __future__ import annotations

import hashlib
import secrets
from dataclasses import dataclass
from uuid import UUID, uuid4

from app.kernel.store.models import AgentDefinition, Org, Principal, User, UserToken
from app.kernel.store.service import session

ORG_NAMES = ("Org A", "Org B")
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
        org_id, system_principal_id, user_id = uuid4(), uuid4(), uuid4()
        token = secrets.token_urlsafe(32)
        async with session(org_id, system_principal_id) as scoped:
            scoped.add(Org(id=org_id, name=name))
            scoped.add(
                Principal(id=system_principal_id, org_id=org_id, class_="system")
            )
            scoped.add(User(id=user_id, org_id=org_id, display_name=f"{name} owner"))
            scoped.add(
                Principal(id=uuid4(), org_id=org_id, class_="user", user_id=user_id)
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
            await scoped.commit()
        seeded.append(SeededOrg(org_id, system_principal_id, user_id, token))
    return seeded
