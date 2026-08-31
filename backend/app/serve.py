"""The serve role's front door: a bearer token becomes an org-scoped session.

Every router takes these two dependencies and nothing else authenticates, so the
route bodies never see a token and cannot open a session that is not the caller's.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.kernel.identity.service import Caller, resolve
from app.kernel.store.service import session

_bearer = HTTPBearer()


async def caller(
    credentials: Annotated[HTTPAuthorizationCredentials, Depends(_bearer)],
) -> Caller:
    """The token's org and principal; 401 for one that is unknown or revoked."""
    who = await resolve(credentials.credentials)
    if who is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "unknown or revoked token")
    return who


Who = Annotated[Caller, Depends(caller)]


async def scoped(who: Who) -> AsyncGenerator[AsyncSession]:
    """The request's session, committed when the route returns and rolled back
    when it raises, because the exception reaches this generator at the yield."""
    async with session(who.org_id, who.principal_id) as request_session:
        yield request_session
        await request_session.commit()


Scoped = Annotated[AsyncSession, Depends(scoped)]
