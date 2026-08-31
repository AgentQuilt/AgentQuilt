"""What identity promises: the token names one principal, and an approval spends once.

Every test runs against a real Postgres through a scoped session, because the org
in the consume predicate is the session's and RLS is what makes it true.
"""

from __future__ import annotations

import hashlib
from datetime import timedelta
from uuid import UUID, uuid4

import pytest
from sqlalchemy import Select, select

from app.kernel.declare.models import Json
from app.kernel.identity.models import Approval, Grant
from app.kernel.identity.service import (
    Consume,
    args_hash,
    consume_approval,
    effective_grants,
    resolve,
)
from app.kernel.store.models import Principal, UserToken
from app.kernel.store.seed import UNDOABLE_OPERATION, SeededOrg, seed
from app.kernel.store.service import session
from tests.kit import START, FakeClock
from tests.kit_notes import notes_registry

pytestmark = pytest.mark.anyio

REVOKED = "revoked-token"
RUN = UUID("11111111-1111-1111-1111-111111111111")
ARGS: Json = {"note_id": str(RUN), "body": "hello"}


@pytest.fixture(scope="module")
async def org(migrated_url: str) -> SeededOrg:
    """An org of this module's own: its token and user are what `resolve` reads."""
    return (await seed())[0]


@pytest.fixture(scope="module")
async def version_id(org: SeededOrg) -> str:
    """An `operation_version` row to hang approvals off; the toy kit publishes it."""
    registry = notes_registry()
    async with session(org.org_id, org.system_principal_id) as scoped:
        await registry.publish(scoped)
        await scoped.commit()
    return registry.version_id(registry.get("note.write_note"))


def _approval(org: SeededOrg, version_id: str, digest: str, state: str) -> Approval:
    return Approval(
        id=uuid4(),
        org_id=org.org_id,
        granted_to=org.system_principal_id,
        operation_version_id=version_id,
        args_hash=digest,
        state=state,
        run_id=RUN,
        step_no=1,
        tool_call_id="tc-approval",
        expires_at=START + timedelta(hours=1),
    )


def _state(approval_id: UUID) -> Select[tuple[str]]:
    """Read the row back rather than the mapped object: the UPDATE bypassed it."""
    return select(Approval.state).where(Approval.id == approval_id)


def _consume(org: SeededOrg, version_id: str, digest: str) -> Consume:
    return Consume(
        granted_to=org.system_principal_id,
        operation_version_id=version_id,
        args_hash=digest,
        action_id=uuid4(),
        now=FakeClock().now(),
    )


async def test_resolve_token(org: SeededOrg) -> None:
    """The read serve makes before it has a session, so it takes only the token."""
    caller = await resolve(org.token)
    assert caller is not None
    assert caller.org_id == org.org_id
    async with session(org.org_id, org.system_principal_id) as scoped:
        assert (
            await scoped.scalar(
                select(Principal.user_id).where(Principal.id == caller.principal_id)
            )
            == org.user_id
        )
        scoped.add(
            UserToken(
                id=uuid4(),
                user_id=org.user_id,
                org_id=org.org_id,
                token_hash=hashlib.sha256(REVOKED.encode()).hexdigest(),
                revoked_at=START,
            )
        )
        await scoped.commit()

    assert await resolve("no-such-token") is None
    assert await resolve(REVOKED) is None


async def test_effective_grants_maps_rows(org: SeededOrg) -> None:
    async with session(org.org_id, org.system_principal_id) as scoped:
        for name, level in (("note.write_note", "asks_first"), ("note.x", "never")):
            scoped.add(
                Grant(
                    id=uuid4(),
                    org_id=org.org_id,
                    principal_id=org.system_principal_id,
                    operation_name=name,
                    level=level,
                )
            )
        await scoped.flush()
        assert await effective_grants(scoped, org.system_principal_id) == {
            # The seeded grant is in the map too: it is a row like any other.
            UNDOABLE_OPERATION: "asks_first",
            "note.write_note": "asks_first",
            "note.x": "never",
        }
        assert await effective_grants(scoped, uuid4()) == {}


def test_args_hash_is_order_independent() -> None:
    reordered: Json = {"body": ARGS["body"], "note_id": ARGS["note_id"]}
    assert args_hash("v1", ARGS) == args_hash("v1", reordered)
    assert args_hash("v1", ARGS | {"body": "other"}) != args_hash("v1", ARGS)
    assert args_hash("v2", ARGS) != args_hash("v1", ARGS)


async def test_consume_requires_open_and_binding(
    org: SeededOrg, version_id: str
) -> None:
    digest = args_hash(version_id, ARGS)
    other_digest = args_hash(version_id, ARGS | {"body": "b"})
    async with session(org.org_id, org.system_principal_id) as scoped:
        opened = _approval(org, version_id, digest, "open")
        scoped.add(opened)
        scoped.add(_approval(org, version_id, other_digest, "requested"))
        await scoped.flush()

        request = _consume(org, version_id, digest)
        assert await consume_approval(scoped, request) == opened.id
        assert await consume_approval(scoped, request) is None
        still_requested = _consume(org, version_id, other_digest)
        assert await consume_approval(scoped, still_requested) is None

        # A second open row, so a changed digest failing is the binding and not
        # the absence of anything to spend.
        again = _approval(org, version_id, digest, "open")
        scoped.add(again)
        await scoped.flush()
        rebound = _consume(org, version_id, args_hash(version_id, ARGS | {"body": "x"}))
        assert await consume_approval(scoped, rebound) is None
        assert await scoped.scalar(_state(again.id)) == "open"


async def test_expired_open_approval_does_not_consume(
    org: SeededOrg, version_id: str
) -> None:
    clock = FakeClock()
    digest = args_hash(version_id, ARGS | {"body": "expired"})
    async with session(org.org_id, org.system_principal_id) as scoped:
        stale = _approval(org, version_id, digest, "open")
        stale.expires_at = clock.now() - timedelta(hours=1)
        scoped.add(stale)
        await scoped.flush()
        assert await consume_approval(scoped, _consume(org, version_id, digest)) is None
        assert await scoped.scalar(_state(stale.id)) == "open"
