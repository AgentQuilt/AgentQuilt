"""The serve role's front door: a bearer token becomes an org-scoped session.

Every router takes these two dependencies and nothing else authenticates, so the
route bodies never see a token and cannot open a session that is not the caller's.
The one route here is the QA harness page, which carries no data of its own and is
the only thing this app serves without a token.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import FileResponse
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


router = APIRouter()
# One self-contained file next to this one: no build step and no second asset to
# serve, so the page ships wherever the package does.
HARNESS = Path(__file__).resolve().parent / "harness.html"


@router.get("/", response_class=FileResponse, include_in_schema=False)
async def harness() -> FileResponse:
    """The QA harness page. Static, so it needs no token; every call it makes
    from the browser carries the one the person pastes into it."""
    return FileResponse(HARNESS, media_type="text/html")
