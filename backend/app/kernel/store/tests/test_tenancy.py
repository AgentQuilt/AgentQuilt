"""Isolation through the store interface: what one org sees, and what it may write.

The migration tests prove RLS from a raw connection; these prove the session
carries the scope, which is the thing every kernel module will depend on.
"""

from __future__ import annotations

from uuid import UUID, uuid4

import pytest
from alembic.autogenerate import compare_metadata
from alembic.runtime.migration import MigrationContext
from sqlalchemy import Connection, select, text
from sqlalchemy.exc import DBAPIError, ProgrammingError
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from app.kernel.declare.models import IdempotencyKey
from app.kernel.store.models import Base, Org, User
from app.kernel.store.seed import SeededOrg, seed
from app.kernel.store.service import engine, session
from tests.kit import Scope, two_principals

pytestmark = pytest.mark.anyio


@pytest.fixture(scope="module")
async def scopes(migrated_url: str) -> tuple[Scope, Scope]:
    return await two_principals(migrated_url)


async def test_org_b_cannot_read_org_a_rows(scopes: tuple[Scope, Scope]) -> None:
    (org_a, _, _), (org_b, _, _) = scopes
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
    (_, _, _), (org_b, _, _) = scopes
    async with session(*scopes[0]) as scoped:
        scoped.add(User(id=uuid4(), org_id=org_b, display_name="planted"))
        with pytest.raises(ProgrammingError, match="row-level security"):
            await scoped.flush()


@pytest.fixture(scope="module")
async def org(migrated_url: str) -> SeededOrg:
    """One org and both its planes: the plane cases need the dev one by id."""
    first, _ = await seed()
    return first


def _key(org_id: UUID, name: str) -> IdempotencyKey:
    """The one env-scoped row that hangs off nothing, so a plane case can write
    it without first building a run, an event and an action to point at."""
    return IdempotencyKey(org_id=org_id, operation_name=name, idempotency_key=name)


async def test_session_without_the_plane_fails_closed(
    migrated_url: str, org: SeededOrg
) -> None:
    """The org GUC alone buys nothing. Its own engine, so the connection has
    never carried a plane: the read is empty though the org owns rows, and the
    write has no plane to default from."""
    async with session(
        org.org_id, org.prod_environment_id, org.system_principal_id
    ) as scoped:
        scoped.add(_key(org.org_id, "planed"))
        await scoped.commit()
    unplaned = create_async_engine(migrated_url)
    try:
        async with AsyncSession(unplaned) as plain:
            await plain.execute(text("SET LOCAL ROLE agentquilt_app"))
            await plain.execute(
                text("SELECT set_config('app.org_id', :org, true)"),
                {"org": str(org.org_id)},
            )
            rows = await plain.execute(select(IdempotencyKey.idempotency_key))
            assert rows.scalars().all() == []
            plain.add(_key(org.org_id, "unplaned"))
            with pytest.raises(DBAPIError):
                await plain.flush()
    finally:
        await unplaned.dispose()


async def test_dev_plane_cannot_read_a_prod_row(org: SeededOrg) -> None:
    """Same org, other plane: two-key policies hide it exactly as one key hides
    another org's."""
    prod = (org.org_id, org.prod_environment_id, org.system_principal_id)
    dev = (org.org_id, org.dev_environment_id, org.system_principal_id)
    async with session(*prod) as scoped:
        scoped.add(_key(org.org_id, "prod-only"))
        await scoped.commit()
    async with session(*dev) as scoped:
        seen = (await scoped.execute(select(IdempotencyKey.idempotency_key))).scalars()
        assert list(seen) == []
    async with session(*prod) as scoped:
        seen = (await scoped.execute(select(IdempotencyKey.idempotency_key))).scalars()
        assert "prod-only" in list(seen)


# The rail is mapped as of 0004; what is left ahead of the models is the one
# column wave E2 pins by code, skipped the way a table the models do not carry
# at all is skipped.
RAIL_COLUMNS = frozenset({"tier_binding_version"})


def _drift(connection: Connection) -> list[object]:
    def include_name(name: str | None, type_: str, parents: dict[str, str]) -> bool:
        if type_ == "schema":
            return name in ("core", "mod_skills")
        if type_ == "table":
            return parents["schema_qualified_table_name"] in Base.metadata.tables
        return type_ != "column" or name not in RAIL_COLUMNS

    context = MigrationContext.configure(
        connection, opts={"include_schemas": True, "include_name": include_name}
    )
    return list(compare_metadata(context, Base.metadata))


async def test_models_match_migration(migrated_url: str) -> None:
    async with engine().connect() as connection:
        assert await connection.run_sync(_drift) == []
