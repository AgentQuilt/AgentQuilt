"""The run-less routes: a person's own grants decide, and the ledger records it.

Both routes go through dispatch, so the interesting cases are the two dispatch
answers a route has to turn into HTTP: the operation's own result, and a refusal.
"""

from __future__ import annotations

from uuid import uuid4

import httpx
import pytest
from sqlalchemy import select

from app.kernel.declare.registry import registry
from app.kernel.store.models import Principal
from app.kernel.store.seed import SeededOrg, seed
from app.kernel.store.service import session
from app.modules.governance.service import UNDO
from tests.kit import bearer_client
from tests.kit_notes import grant

pytestmark = pytest.mark.anyio


@pytest.fixture(scope="module")
async def orgs(migrated_url: str) -> tuple[SeededOrg, SeededOrg]:
    """Two orgs: one whose person may undo, one whose person was granted nothing."""
    granted, ungranted = await seed()
    async with session(granted.org_id, granted.system_principal_id) as scoped:
        await registry.publish(scoped)
        person = (
            await scoped.scalars(select(Principal.id).where(Principal.class_ == "user"))
        ).one()
        await grant(scoped, person, UNDO, "may_use")
        await scoped.commit()
    return granted, ungranted


def _client(serve_url: str, org: SeededOrg) -> httpx.AsyncClient:
    return bearer_client(serve_url, org.token)


async def test_undo_route_returns_the_refusal(
    serve_url: str, orgs: tuple[SeededOrg, SeededOrg]
) -> None:
    granted, _ = orgs
    async with _client(serve_url, granted) as client:
        response = await client.post(f"/actions/{uuid4()}/undo")
    assert response.status_code == 200
    assert response.json()["undo_run_id"] is None


async def test_ungranted_person_is_denied(
    serve_url: str, orgs: tuple[SeededOrg, SeededOrg]
) -> None:
    _, ungranted = orgs
    async with _client(serve_url, ungranted) as client:
        response = await client.post(f"/actions/{uuid4()}/undo")
    assert response.status_code == 403
    assert response.json()["detail"] == "no_grant"
