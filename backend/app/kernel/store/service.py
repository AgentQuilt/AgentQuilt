"""The one way into the database: a session is always scoped to an org, a plane and
a principal.

There is no unscoped session here on purpose. All three arguments are required, so a
caller cannot reach a row without saying whose it is and which plane it is on, and the
tenant settings are transaction-scoped (`SET LOCAL` in `after_begin`), never
connection-scoped: a pooled connection handed to the next org carries nothing over.
"""

from __future__ import annotations

import os
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from functools import cache
from uuid import UUID

from sqlalchemy import Connection, event, select, text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import Session, SessionTransaction

from app.kernel.store.models import Environment, Principal

# An org, the plane its activity is on and the principal acting: what every scoped
# session is opened with, and what `tenants` hands the background roles.
Scope = tuple[UUID, UUID, UUID]

# SET LOCAL takes no bind parameters, so the three tenant settings go through
# set_config(..., is_local => true), which is the same thing and does.
_SCOPE = text(
    "SELECT set_config('app.org_id', :org, true),"
    " set_config('app.environment_id', :environment, true),"
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


async def tenants() -> list[Scope]:
    """Every plane of every org, and the system principal a background role acts as.

    The one read a background role cannot make org-scoped: `work` and `tick`
    serve all tenants and have to find them before they can open a session. It
    runs as the connecting role rather than `agentquilt_app`, and so needs a role
    that row-level security does not filter. Harness workaround, 2026-08-30:
    migration 0001 grants its policies to `agentquilt_app` alone under FORCE RLS,
    so this reads everything only as a superuser; the role a deployment connects
    with is a migration this wave did not open. Trigger: the first deployment
    that is not a local container. The class, one connecting-role read each:
    this, identity's `resolve`, and — since the rail — its `locate` and
    `prod_plane`.
    """
    async with engine().connect() as connection:
        rows = await connection.execute(
            select(Principal.org_id, Environment.id, Principal.id)
            .join(Environment, Environment.org_id == Principal.org_id)
            .where(Principal.class_ == "system")
            .order_by(Principal.org_id, Environment.key)
        )
        return [(org, environment, principal) for org, environment, principal in rows]


@asynccontextmanager
async def session(
    org_id: UUID, environment_id: UUID, principal_id: UUID
) -> AsyncGenerator[AsyncSession]:
    sessions = async_sessionmaker(
        engine(), sync_session_class=_ScopedSession, expire_on_commit=False
    )
    async with sessions(
        info={
            "org": str(org_id),
            "environment": str(environment_id),
            "principal": str(principal_id),
        }
    ) as scoped:
        yield scoped
