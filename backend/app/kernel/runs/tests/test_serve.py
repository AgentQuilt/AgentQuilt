"""The web thread over a real socket: a token opens one, and its stream resumes.

The client talks to a uvicorn on a port rather than to the app through an ASGI
transport, because what is under test is a reader that hangs up in the middle of
a response and comes back with the cursor it stopped at.
"""

from __future__ import annotations

import json
from uuid import UUID, uuid4

import httpx
import pytest

from app.kernel.runs.service import cancel
from app.kernel.store.seed import SeededOrg, seed
from app.kernel.store.service import session

pytestmark = pytest.mark.anyio


@pytest.fixture(scope="module")
async def org(migrated_url: str) -> SeededOrg:
    """An org of this module's own; the token `seed` prints is what serve reads."""
    return (await seed())[0]


def _client(serve_url: str, org: SeededOrg) -> httpx.AsyncClient:
    return httpx.AsyncClient(
        base_url=serve_url, headers={"Authorization": f"Bearer {org.token}"}
    )


async def _frame(client: httpx.AsyncClient, url: str, cursor: int) -> dict[str, str]:
    """Read one SSE frame and hang up, which is what a browser reload does."""
    headers = {"Last-Event-ID": str(cursor)} if cursor else {}
    fields: dict[str, str] = {}
    async with client.stream("GET", url, headers=headers) as response:
        assert response.status_code == 200
        async for line in response.aiter_lines():
            if line:
                name, _, value = line.partition(": ")
                fields[name] = value
            elif fields:
                return fields
    pytest.fail(f"{url} closed before it sent an event")


async def test_unknown_token_is_refused(serve_url: str) -> None:
    async with httpx.AsyncClient(base_url=serve_url) as client:
        response = await client.post(
            "/threads", headers={"Authorization": "Bearer no-such-token"}
        )
    assert response.status_code == 401


async def test_message_to_an_unknown_run_is_not_found(
    serve_url: str, org: SeededOrg
) -> None:
    async with _client(serve_url, org) as client:
        response = await client.post(f"/runs/{uuid4()}/messages", json={"text": "hi"})
    assert response.status_code == 404


async def test_events_stream_and_replay(serve_url: str, org: SeededOrg) -> None:
    async with _client(serve_url, org) as client:
        opened = await client.post("/threads")
        assert opened.status_code == 201
        run_id = UUID(opened.json()["run_id"])
        stream = f"/runs/{run_id}/events"

        steered = await client.post(f"/runs/{run_id}/messages", json={"text": "hello"})
        assert steered.status_code == 202
        assert steered.json() == {"seq": 1}

        created = await _frame(client, stream, 0)
        assert created["event"] == "run_journal"
        assert json.loads(created["data"])["payload"]["event"] == "run.created"

        # The second event lands while nobody is reading, so the reconnect is the
        # only thing that can deliver it.
        async with session(org.org_id, org.system_principal_id) as scoped:
            assert await cancel(scoped, run_id)
            await scoped.commit()

        resumed = await _frame(client, stream, int(created["id"]))
        # The run has two events: the reconnect repeated neither and skipped
        # nothing, so it starts at the one the first reader never saw.
        assert int(resumed["id"]) > int(created["id"])
        assert json.loads(resumed["data"])["payload"]["event"] == "run.cancelled"
