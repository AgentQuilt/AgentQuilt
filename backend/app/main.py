"""AgentQuilt process entrypoint: one image, four roles (ADR-0011)."""

from __future__ import annotations

import argparse
import asyncio
import importlib

from fastapi import FastAPI

from app.kernel.declare.catalog import PAGE, render
from app.kernel.declare.registry import registry
from app.kernel.store.seed import seed

ROLES = ("serve", "work", "tick", "seed")

# The ASGI target the `serve` role will be started against; empty until wave 9.
app = FastAPI()


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
    print(f"agentquilt: role {args.role}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
