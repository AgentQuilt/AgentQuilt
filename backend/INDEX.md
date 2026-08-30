# backend

- `app/main.py` — the `agentquilt serve | work | tick | seed` entrypoint (one image, four roles).
- `app/kernel/` — the kernel modules and `ports/`; `KERNEL.md` maps them, `FROZEN.md` states the change protocol.
- `app/modules/` — buildable modules on top of the kernel; empty until wave 9.
- `migrations/` — the Alembic async chain (`env.py`) and `lint.py`, the naming check pytest runs.
- `migrations/versions/` — `0001_create_spine.py`: schemas `core` and `mod_skills`, the two roles, the tenant and ledger tables, RLS and grants.
- `tests/` — real Postgres through testcontainers; no DB mocks.

Gates, from this directory: `uv run ruff check .`, `uv run pyright`, `uv run pytest` (traps in AGENTS.md, Gates).
Postgres for Alembic and psql: `docker compose up -d db` at the repo root, then `DATABASE_URL=postgresql+psycopg://agentquilt:agentquilt@localhost:5432/agentquilt uv run alembic upgrade head`; `DATABASE_URL` is the only database setting (`alembic.ini` carries no URL; the compose services get it from `compose.yaml`).
