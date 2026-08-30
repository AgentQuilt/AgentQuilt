"""AgentQuilt process entrypoint: one image, four roles (ADR-0011)."""

from __future__ import annotations

import argparse
import asyncio
import importlib
import os
import socket

from fastapi import FastAPI

from app.kernel.declare.catalog import PAGE, render
from app.kernel.declare.registry import registry
from app.kernel.model.adapter import PydanticAIModelRunner
from app.kernel.runs.tick import tick_once
from app.kernel.runs.work import work_once
from app.kernel.store.seed import seed
from app.kernel.store.service import tenants

ROLES = ("serve", "work", "tick", "seed")
# ADR-0019: one-second polling is fine at this scale, and LISTEN/NOTIFY waits
# for a measured idle-poll cost.
POLL_SECONDS = 1.0

# The ASGI target the `serve` role will be started against; empty until wave 9.
app = FastAPI()


async def work() -> None:
    """The `work` role: claim and work one step per tenant, forever.

    `SKIP LOCKED` is what makes N of these safe against each other, so the loop
    itself needs no coordination — only a name to lease under.
    """
    importlib.import_module("app.modules")
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
    """The `tick` role: one pass per tenant; the advisory lock picks the leader."""
    for scope in await tenants():
        await tick_once(scope)


def main() -> int:
    parser = argparse.ArgumentParser(prog="agentquilt")
    subparsers = parser.add_subparsers(dest="role", required=True)
    # `catalog` is a one-shot that regenerates the operations page, not a role.
    for command in (*ROLES, "catalog"):
        subparsers.add_parser(command)
    args = parser.parse_args()
    if args.role == "catalog":
        # Importing the modules package is what declares their operations.
        importlib.import_module("app.modules")
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
    print(f"agentquilt: role {args.role}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
