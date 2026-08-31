"""The schema chain, addressed by absolute path so the caller's cwd cannot matter.

One home for it: the `migrate` role runs it against the deployment's database and
the test session runs it against a container, and both mean the same chain.
"""

from __future__ import annotations

from pathlib import Path

from alembic.config import Config

BACKEND = Path(__file__).resolve().parents[3]


def alembic_config() -> Config:
    config = Config(str(BACKEND / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND / "migrations"))
    return config
