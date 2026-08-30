"""The first module operation: a person answers one parked call.

Deciding is itself a declared operation, so the answer lands in the ledger with
the same action, grant check and idempotency key as any other write, and nothing
about approvals needs a second write path. The decision moves the approval and
then, in the same transaction, hands the run back to the queue it parked from.
"""

from __future__ import annotations

from typing import Literal
from uuid import UUID

from pydantic import BaseModel
from sqlalchemy import text

from app.kernel.declare.models import Json
from app.kernel.declare.registry import CallContext, Declares, registry
from app.kernel.identity.models import Approval
from app.kernel.store.models import Principal

NAME = "governance.decide_approval"
# Only a person or the system decides an approval (ADR-0004): an agent that could
# approve its own parked call is the whole point of the gate defeated.
DECIDERS = ("user", "system")

# The run is handed back guarded: only a run still waiting on this answer moves,
# and the queue row goes in only when the guard matched, so a cancelled or
# already-running run is decided without being enqueued twice. Raw SQL because
# `core.run` and `core.step_queue` are mapped in wave 8, not here.
_QUEUE_RUN = text(
    "UPDATE core.run SET state = 'queued', updated_at = now()"
    " WHERE id = :run AND state = 'waiting_approval' RETURNING id"
)
_ENQUEUE_STEP = text(
    "INSERT INTO core.step_queue (org_id, run_id, step_no, queue_tag)"
    " VALUES (:org, :run, :step, 'main')"
)


class DecideApproval(BaseModel):
    approval_id: UUID
    decision: Literal["approve", "reject"]
    reason: str | None = None


@registry.operation(NAME, Declares(mode="write", reversal="irreversible"))
async def decide_approval(ctx: CallContext, args: DecideApproval) -> Json:
    """Approve or reject one parked call, and re-queue the step it parked."""
    # Under the row lock, so two deciders answering at once cannot both move it.
    approval = await ctx.session.get(Approval, args.approval_id, with_for_update=True)
    if approval is None or approval.state != "requested":
        return {"decided": False, "state": approval.state if approval else None}

    decider = await ctx.session.get(Principal, ctx.principal_id)
    if decider is None or decider.class_ not in DECIDERS:
        raise ValueError(f"{NAME}: a principal of class {DECIDERS} decides an approval")

    if args.decision == "approve":
        approval.state = "open"
        approval.granted_by = ctx.principal_id
    else:
        approval.state = "rejected"
        approval.reason = args.reason
    await ctx.session.flush()

    queued = await ctx.session.scalar(_QUEUE_RUN, {"run": approval.run_id})
    if queued is not None:
        await ctx.session.execute(
            _ENQUEUE_STEP,
            {
                "org": UUID(ctx.session.info["org"]),
                "run": approval.run_id,
                "step": approval.step_no,
            },
        )
    return {"decided": True, "state": approval.state, "run_queued": queued is not None}
