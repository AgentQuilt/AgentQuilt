"""AgentQuilt process entrypoint: one image, four roles (ADR-0011)."""

from __future__ import annotations

import argparse

from fastapi import FastAPI

ROLES = ("serve", "work", "tick", "seed")

# The ASGI target the `serve` role will be started against; empty until wave 3.
app = FastAPI()


def main() -> int:
    parser = argparse.ArgumentParser(prog="agentquilt")
    subparsers = parser.add_subparsers(dest="role", required=True)
    for role in ROLES:
        subparsers.add_parser(role)
    args = parser.parse_args()
    print(f"agentquilt: role {args.role}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
