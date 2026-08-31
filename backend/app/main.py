"""AgentQuilt process entrypoint: one image, four roles (ADR-0011)."""

from __future__ import annotations

import argparse
import asyncio
import importlib
import os
import socket

import uvicorn
from alembic import command
from fastapi import FastAPI

from app.kernel.declare.catalog import PAGE, render
from app.kernel.declare.registry import registry
from app.kernel.model.adapter import PydanticAIModelRunner
from app.kernel.runs.router import router as runs_router
from app.kernel.runs.tick import tick_once
from app.kernel.runs.work import work_once
from app.kernel.store.migrate import alembic_config
from app.kernel.store.seed import seed
from app.kernel.store.service import tenants
from app.modules.governance.router import router as governance_router
from app.serve import router as harness_router

ROLES = ("serve", "work", "tick", "seed")
# ADR-0019: one-second polling is fine at this scale, and LISTEN/NOTIFY waits
# for a measured idle-poll cost.
POLL_SECONDS = 1.0

# Importing the modules package is what declares their operations, for the
# catalog and for dispatch alike; the two routers plus the harness page are the
# whole HTTP surface.
importlib.import_module("app.modules")
app = FastAPI()
app.include_router(runs_router)
app.include_router(governance_router)
app.include_router(harness_router)


async def work() -> None:
    """The `work` role: claim and work one step per tenant, forever.

    `SKIP LOCKED` is what makes N of these safe against each other, so the loop
    itself needs no coordination — only a name to lease under.
    """
    runner = PydanticAIModelRunner()
    worker_id = f"{socket.gethostname()}:{os.getpid()}"
    while True:
        worked = [
            await work_once(
                scope, worker_id=worker_id, runner=runner, registry=registry
            )
            for scope in await tenants()
        ]
        if not any(state is not None for state in worked):
            await asyncio.sleep(POLL_SECONDS)


async def tick() -> None:
    """The `tick` role: reap and expire every tenant, forever; the advisory lock
    picks the leader each pass."""
    while True:
        for scope in await tenants():
            await tick_once(scope)
        await asyncio.sleep(POLL_SECONDS)


def main() -> int:
    parser = argparse.ArgumentParser(prog="agentquilt")
    subparsers = parser.add_subparsers(dest="role", required=True)
    # `migrate` and `catalog` are one-shots, not roles: the chain to head, and
    # the operations page regenerated.
    for name in (*ROLES, "migrate", "catalog"):
        subparsers.add_parser(name)
    args = parser.parse_args()
    if args.role == "migrate":
        command.upgrade(alembic_config(), "head")
        return 0
    if args.role == "catalog":
        PAGE.write_text(render(registry))
        print(f"agentquilt: wrote {PAGE}")
        return 0
    if args.role == "seed":
        for org in asyncio.run(seed()):
            print(f"org {org.org_id} user {org.user_id} token {org.token}")
        return 0
    if args.role in ("work", "tick"):
        asyncio.run(work() if args.role == "work" else tick())
        return 0
    # What is left is `serve`. The app binds every interface because the
    # container is what decides which of them reaches the port.
    uvicorn.run(app, host="0.0.0.0", port=8000)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
