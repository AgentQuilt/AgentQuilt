"""The one way into the database: a session is always scoped to an org and a principal.

There is no unscoped session here on purpose. Both arguments are required, so a
caller cannot reach a row without saying whose it is, and the tenant settings are
transaction-scoped (`SET LOCAL` in `after_begin`), never connection-scoped: a pooled
connection handed to the next org carries nothing over.
"""

from __future__ import annotations

import os
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from functools import cache
from uuid import UUID

from sqlalchemy import Connection, event, text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import Session, SessionTransaction

# SET LOCAL takes no bind parameters, so the two tenant settings go through
# set_config(..., is_local => true), which is the same thing and does.
_SCOPE = text(
    "SELECT set_config('app.org_id', :org, true),"
    " set_config('app.principal_id', :principal, true)"
)


class _ScopedSession(Session):
    """Event target: the listener below must not reach a session opened elsewhere."""


def _apply_scope(
    session: Session, transaction: SessionTransaction, connection: Connection
) -> None:
    connection.exec_driver_sql("SET LOCAL ROLE agentquilt_app")
    connection.execute(_SCOPE, session.info)


event.listen(_ScopedSession, "after_begin", _apply_scope)


@cache
def engine() -> AsyncEngine:
    return create_async_engine(os.environ["DATABASE_URL"])


@asynccontextmanager
async def session(org_id: UUID, principal_id: UUID) -> AsyncGenerator[AsyncSession]:
    sessions = async_sessionmaker(
        engine(), sync_session_class=_ScopedSession, expire_on_commit=False
    )
    async with sessions(
        info={"org": str(org_id), "principal": str(principal_id)}
    ) as scoped:
        yield scoped
