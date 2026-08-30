from collections.abc import Iterator

import pytest
from testcontainers.community.postgres import PostgresContainer


@pytest.fixture(scope="session")
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture(scope="session")
def postgres_url() -> Iterator[str]:
    """A real Postgres 17 for the session; no DB mocks anywhere in this suite."""
    with PostgresContainer("postgres:17", driver="psycopg") as container:
        yield container.get_connection_url()
