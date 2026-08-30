"""One model call: the budget check, the runner, the usage row, the telemetry.

The cap is checked before the call and not after, because tokens spent cannot be
returned; a refusal is a `denial` in the ledger (ADR-0002), so a run that stopped
short says so in the same place every other refusal is read.
"""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID, uuid4

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.kernel.context.models import ContextManifest
from app.kernel.context.service import AssembledTurn, tokens
from app.kernel.declare.ledger import Append, append
from app.kernel.declare.models import Event
from app.kernel.model.models import UsageRecord
from app.kernel.ports.model_runner import Completion, ModelRunner
from app.kernel.store.models import Json, Run

BUDGET_EXCEEDED = "budget_exceeded"


@dataclass(frozen=True, slots=True)
class Answered:
    """The provider answered; the cost is already in `core.usage_record`."""

    completion: Completion


@dataclass(frozen=True, slots=True)
class Refused:
    """No call was made; `event` is the denial the ledger now carries."""

    reason: str
    event: Event


Outcome = Answered | Refused


async def run(
    session: AsyncSession,
    assembled: AssembledTurn,
    run_row: Run,
    *,
    runner: ModelRunner,
) -> Outcome:
    """Answer one assembled turn, or refuse it against the run's budget cap."""
    manifest = await session.get_one(ContextManifest, assembled.manifest_id)
    spent = await _spent(session, run_row.id)
    if spent + assembled.token_cost > run_row.budget_cap_tokens:
        payload: Json = {
            "reason": BUDGET_EXCEEDED,
            "spent_tokens": spent,
            "estimated_tokens": assembled.token_cost,
            "budget_cap_tokens": run_row.budget_cap_tokens,
        }
        return Refused(BUDGET_EXCEEDED, await _deny(session, manifest, payload))

    completion = await runner.run(assembled, assembled.binding)
    # ADR-0014's mandatory position is where the prefix ends. It is recorded for
    # every provider and handed only to one with a cache API, which the generic
    # request path is not, so this row is the only place it lands.
    manifest.cache_positions = {
        "prefix_end_tokens": sum(tokens(layer.body) for layer in assembled.prefix)
    }
    manifest.telemetry = completion.cache
    session.add(
        UsageRecord(
            id=uuid4(),
            org_id=UUID(session.info["org"]),
            run_id=run_row.id,
            step_no=manifest.step_no,
            tier=assembled.tier,
            input_tokens=completion.usage.input_tokens,
            output_tokens=completion.usage.output_tokens,
            cached_tokens=completion.usage.cached_tokens,
        )
    )
    await session.flush()
    return Answered(completion)


async def _spent(session: AsyncSession, run_id: UUID) -> int:
    """What this run has cost so far. Cached input is billed, so both of the
    counts the provider charges for are counted here."""
    total = await session.scalar(
        select(
            func.coalesce(
                func.sum(UsageRecord.input_tokens + UsageRecord.output_tokens), 0
            )
        ).where(UsageRecord.run_id == run_id)
    )
    return total or 0


async def _deny(
    session: AsyncSession, manifest: ContextManifest, payload: Json
) -> Event:
    return await append(
        session,
        Append(
            kind="denial",
            aggregate_kind="run",
            aggregate_id=manifest.run_id,
            principal_id=UUID(session.info["principal"]),
            payload=payload,
            run_id=manifest.run_id,
            step_no=manifest.step_no,
        ),
    )
