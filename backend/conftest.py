import os
from collections.abc import Iterator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from testcontainers.community.postgres import PostgresContainer

BACKEND = Path(__file__).resolve().parent


@pytest.fixture(scope="session")
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture(scope="session")
def postgres_url() -> Iterator[str]:
    """A real Postgres 17 for the session; no DB mocks anywhere in this suite."""
    with PostgresContainer("postgres:17", driver="psycopg") as container:
        yield container.get_connection_url()


def alembic_config() -> Config:
    """The chain, addressed by absolute path so pytest's cwd does not matter."""
    config = Config(str(BACKEND / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND / "migrations"))
    return config


@pytest.fixture(scope="session")
def migrated_url(postgres_url: str) -> str:
    """The container at head, with DATABASE_URL set: what `store.engine()` reads."""
    os.environ["DATABASE_URL"] = postgres_url
    command.upgrade(alembic_config(), "head")
    return postgres_url
