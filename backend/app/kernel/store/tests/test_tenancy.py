"""Isolation through the store interface: what one org sees, and what it may write.

The migration tests prove RLS from a raw connection; these prove the session
carries the scope, which is the thing every kernel module will depend on.
"""

from __future__ import annotations

from uuid import uuid4

import pytest
from alembic.autogenerate import compare_metadata
from alembic.runtime.migration import MigrationContext
from sqlalchemy import Connection, select, text
from sqlalchemy.exc import ProgrammingError
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from app.kernel.store.models import Base, Org, User
from app.kernel.store.service import engine, session
from tests.kit import Scope, two_principals

pytestmark = pytest.mark.anyio


@pytest.fixture(scope="module")
async def scopes(migrated_url: str) -> tuple[Scope, Scope]:
    return await two_principals(migrated_url)


async def test_org_b_cannot_read_org_a_rows(scopes: tuple[Scope, Scope]) -> None:
    (org_a, _), (org_b, _) = scopes
    async with session(*scopes[1]) as scoped:
        orgs = (await scoped.execute(select(Org.id))).scalars().all()
        users = (await scoped.execute(select(User.org_id))).scalars().all()
    async with session(*scopes[0]) as scoped:
        theirs = (await scoped.execute(select(Org.id))).scalars().all()
    assert list(orgs) == [org_b]
    assert set(users) == {org_b}
    assert list(theirs) == [org_a]


async def test_unscoped_session_sees_nothing(migrated_url: str) -> None:
    # Its own engine, so the connection has never carried a scope: on a pooled
    # one the reset value of app.org_id is '', and the read raises instead of
    # returning nothing. Fail closed either way, empty only on a fresh session.
    unscoped = create_async_engine(migrated_url)
    try:
        async with AsyncSession(unscoped) as plain:
            await plain.execute(text("SET LOCAL ROLE agentquilt_app"))
            assert (await plain.execute(select(Org.id))).scalars().all() == []
    finally:
        await unscoped.dispose()


async def test_scoped_write_lands_in_own_org_only(
    scopes: tuple[Scope, Scope],
) -> None:
    (_, _), (org_b, _) = scopes
    async with session(*scopes[0]) as scoped:
        scoped.add(User(id=uuid4(), org_id=org_b, display_name="planted"))
        with pytest.raises(ProgrammingError, match="row-level security"):
            await scoped.flush()


def _drift(connection: Connection) -> list[object]:
    def include_name(name: str | None, type_: str, parents: dict[str, str]) -> bool:
        if type_ == "schema":
            return name == "core"
        if type_ == "table":
            return parents["schema_qualified_table_name"] in Base.metadata.tables
        return True

    context = MigrationContext.configure(
        connection, opts={"include_schemas": True, "include_name": include_name}
    )
    return list(compare_metadata(context, Base.metadata))


async def test_models_match_migration(migrated_url: str) -> None:
    async with engine().connect() as connection:
        assert await connection.run_sync(_drift) == []
