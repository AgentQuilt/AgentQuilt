"""Who a caller is, what they may do, and what an approval is bound to.

A pure function over the two tables, with no port and no policy engine behind it
(ADR-0026): dispatch is the only caller, so when a second evaluator ever appears
these inputs can be serialised without a module changing.
"""

from __future__ import annotations

import hashlib
from collections.abc import Mapping
from typing import Any, cast
from uuid import UUID

import rfc8785
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.kernel.declare.models import Json
from app.kernel.identity.models import Grant
from app.kernel.store.models import Principal, UserToken

# Prefixed and separated so a hash over one field's value can never collide with
# a hash over another's (ADR-0004, the consume-once predicate).
_DOMAIN = b"agentquilt.approval.v1"
_SEPARATOR = b"\x00"


async def resolve(session: AsyncSession, token: str) -> Principal | None:
    """The user principal a live token names, or None for revoked and unknown."""
    return await session.scalar(
        select(Principal)
        .join(UserToken, UserToken.user_id == Principal.user_id)
        .where(
            UserToken.token_hash == hashlib.sha256(token.encode()).hexdigest(),
            UserToken.revoked_at.is_(None),
            Principal.class_ == "user",
        )
    )


async def effective_grants(
    session: AsyncSession, principal_id: UUID
) -> Mapping[str, str]:
    """The step's grants: root ceiling ∩ narrowing state ∩ acting principal's.

    ADR-0015:18 states that intersection. In Phase 1 the narrowing state is always
    empty and the acting principal is the originator, so this one mapping of the
    principal's own `core.grant` rows is the whole of it.
    """
    rows = await session.execute(
        select(Grant.operation_name, Grant.level).where(
            Grant.principal_id == principal_id
        )
    )
    return {name: level for name, level in rows}


def args_hash(operation_version_id: str, args: Json, scope: str = "") -> str:
    """What an approval is bound to: this operation version, these args, this scope."""
    # The ledger types a payload `dict[str, object]` and rfc8785 types the same
    # JSON shape recursively; `dumps` raises on anything that is not JSON, so the
    # cast is checked by the call it feeds.
    canonical = rfc8785.dumps(cast("Mapping[str, Any]", args))
    parts = (_DOMAIN, operation_version_id.encode(), canonical, scope.encode())
    return hashlib.sha256(_SEPARATOR.join(parts)).hexdigest()
