"""Migration 0001 against a real Postgres: the chain, RLS, isolation, append-only.

The table list here is written out rather than imported from the migration, so a
column dropped in the migration fails a test instead of silently agreeing with it.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import psycopg
import pytest
from alembic import command
from alembic.config import Config
from psycopg import sql
from psycopg.errors import InsufficientPrivilege

BACKEND = Path(__file__).resolve().parents[1]

TENANT_TABLES = frozenset(
    {
        "org",
        "user",
        "principal",
        "agent_definition",
        "user_token",
        "role",
        "grant",
        "event",
        "stream_head",
        "action",
        "idempotency_key",
        "approval",
    }
)
GLOBAL_TABLES = frozenset({"operation_version"})

CORE_TABLE_STATE = (
    "SELECT c.relname, c.relrowsecurity, c.relforcerowsecurity FROM pg_class c"
    " JOIN pg_namespace n ON n.oid = c.relnamespace"
    " WHERE n.nspname = 'core' AND c.relkind = 'r'"
)
EVENT_INSERT = (
    "INSERT INTO core.event (org_id, kind, aggregate_kind, aggregate_id,"
    " aggregate_version, principal_id, payload)"
    " VALUES (%s, 'run_journal', 'run', %s, 1, %s, '{}'::jsonb)"
)


def _connect(url: str) -> psycopg.Connection[Any]:
    """A superuser connection; the SQLAlchemy driver tag is not psycopg's to read."""
    return psycopg.connect(url.replace("+psycopg", ""))


def _as_role(url: str, role: str, org: uuid.UUID) -> psycopg.Connection[Any]:
    conn = _connect(url)
    conn.execute("SELECT set_config('app.org_id', %s, false)", (str(org),))
    conn.execute(sql.SQL("SET ROLE {}").format(sql.Identifier(role)))
    return conn


@pytest.fixture(scope="module")
def spine(postgres_url: str) -> Iterator[str]:
    """Upgrade, downgrade to base and upgrade again; the tests read the second head."""
    config = Config(str(BACKEND / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND / "migrations"))
    with pytest.MonkeyPatch.context() as patch:
        patch.setenv("DATABASE_URL", postgres_url)
        command.upgrade(config, "head")
        command.downgrade(config, "base")
        command.upgrade(config, "head")
        yield postgres_url


@pytest.fixture(scope="module")
def orgs(spine: str) -> tuple[uuid.UUID, uuid.UUID]:
    """Two orgs with one user each, inserted as superuser (RLS does not apply)."""
    org_a, org_b = uuid.uuid4(), uuid.uuid4()
    with _connect(spine) as conn:
        for org, label in ((org_a, "A"), (org_b, "B")):
            conn.execute(
                "INSERT INTO core.org (id, name) VALUES (%s, %s)", (org, label)
            )
            conn.execute(
                'INSERT INTO core."user" (id, org_id, display_name)'
                " VALUES (%s, %s, %s)",
                (uuid.uuid4(), org, f"user {label}"),
            )
        conn.commit()
    return org_a, org_b


def test_chain_round_trips_and_creates_every_table(spine: str) -> None:
    with _connect(spine) as conn:
        version = conn.execute("SELECT version_num FROM alembic_version").fetchone()
        tables = conn.execute(CORE_TABLE_STATE).fetchall()
    assert version == ("0001",)
    assert {row[0] for row in tables} == TENANT_TABLES | GLOBAL_TABLES


def test_row_level_security_is_enabled_and_forced_on_tenant_tables(
    spine: str,
) -> None:
    with _connect(spine) as conn:
        state = {
            name: (enabled, forced)
            for name, enabled, forced in conn.execute(CORE_TABLE_STATE).fetchall()
        }
    assert {name: state[name] for name in TENANT_TABLES} == dict.fromkeys(
        TENANT_TABLES, (True, True)
    )
    assert state["operation_version"] == (False, False)


def test_app_role_sees_only_the_org_in_app_org_id(
    spine: str, orgs: tuple[uuid.UUID, uuid.UUID]
) -> None:
    org_a, _ = orgs
    with _as_role(spine, "agentquilt_app", org_a) as conn:
        seen_orgs = conn.execute("SELECT id FROM core.org").fetchall()
        seen_users = conn.execute('SELECT org_id FROM core."user"').fetchall()
    assert seen_orgs == [(org_a,)]
    assert seen_users == [(org_a,)]


def test_only_the_ledger_writer_inserts_events_and_nobody_updates_them(
    spine: str, orgs: tuple[uuid.UUID, uuid.UUID]
) -> None:
    org_a, _ = orgs
    event = (org_a, uuid.uuid4(), uuid.uuid4())
    with _as_role(spine, "agentquilt_app", org_a) as conn:
        with pytest.raises(InsufficientPrivilege):
            conn.execute(EVENT_INSERT, event)
    with _as_role(spine, "agentquilt_ledger_writer", org_a) as conn:
        conn.execute(EVENT_INSERT, event)
        conn.commit()
    for role in ("agentquilt_app", "agentquilt_ledger_writer"):
        with (
            _as_role(spine, role, org_a) as conn,
            pytest.raises(InsufficientPrivilege),
        ):
            conn.execute("UPDATE core.event SET payload = '{}'::jsonb")
