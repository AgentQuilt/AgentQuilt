import asyncio
import os
from collections.abc import AsyncIterator, Iterator

import pytest
import uvicorn
from alembic import command
from testcontainers.community.postgres import PostgresContainer

from app.kernel.store.migrate import alembic_config
from app.main import app


@pytest.fixture(scope="session")
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture(scope="session")
def postgres_url() -> Iterator[str]:
    """A real Postgres 17 for the session; no DB mocks anywhere in this suite."""
    with PostgresContainer("postgres:17", driver="psycopg") as container:
        yield container.get_connection_url()


@pytest.fixture(scope="session")
def migrated_url(postgres_url: str) -> str:
    """The container at head, with DATABASE_URL set: what `store.engine()` reads."""
    os.environ["DATABASE_URL"] = postgres_url
    command.upgrade(alembic_config(), "head")
    return postgres_url


@pytest.fixture(scope="session")
async def serve_url(migrated_url: str) -> AsyncIterator[str]:
    """The app on a real socket for the session.

    A stream test needs a client that can hang up mid-response, and httpx's ASGI
    transport buffers the whole body before it returns one, so an endless SSE
    response never arrives through it.
    """
    server = uvicorn.Server(
        uvicorn.Config(app, host="127.0.0.1", port=0, log_level="warning")
    )
    serving = asyncio.create_task(server.serve())
    while not server.started:
        await asyncio.sleep(0.01)
    yield f"http://127.0.0.1:{server.servers[0].sockets[0].getsockname()[1]}"
    server.should_exit = True
    await serving
