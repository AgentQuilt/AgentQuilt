# One image, four roles: the role is the command (ADR-0011).
FROM python:3.13-slim
COPY --from=ghcr.io/astral-sh/uv:0.12.5 /uv /bin/uv

WORKDIR /app
ENV UV_LINK_MODE=copy UV_COMPILE_BYTECODE=1

COPY backend/pyproject.toml backend/uv.lock /app/
RUN uv sync --locked --no-install-project --no-dev

COPY backend /app
RUN uv sync --locked --no-dev

ENV PATH="/app/.venv/bin:$PATH"
ENTRYPOINT ["agentquilt"]
