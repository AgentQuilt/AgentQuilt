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
from sqlalchemy import func, select, update

from app.kernel.declare.models import Json
from app.kernel.declare.registry import CallContext, Declares, registry
from app.kernel.identity.models import Approval
from app.kernel.runs.models import StepQueue
from app.kernel.runs.service import QUEUE_TAG
from app.kernel.store.models import Principal, Run

NAME = "governance.decide_approval"
# Only a person or the system decides an approval (ADR-0004): an agent that could
# approve its own parked call is the whole point of the gate defeated.
DECIDERS = ("user", "system")

# The run is handed back guarded: only a run still waiting on this answer moves,
# and the queue row goes in only when the guard matched, so a cancelled or
# already-running run is decided without being enqueued twice.


class DecideApproval(BaseModel):
    approval_id: UUID
    decision: Literal["approve", "reject"]
    reason: str | None = None


@registry.operation(NAME, Declares(mode="write", reversal="irreversible"))
async def decide_approval(ctx: CallContext, args: DecideApproval) -> Json:
    """Approve or reject one parked call, and re-queue the step it parked."""
    # Who may decide comes first: an unauthorized decider learns nothing, not
    # even whether the approval exists or was already answered.
    # ADR-0004 closed the self-approval door for agents; a step's dispatch runs
    # as the system principal, so the class check alone would leave it open — and
    # a step deciding another run's approval locks a foreign run row, the one
    # cross-run path that could deadlock two workers (runs/MODULE.md lock order).
    if ctx.run_id is not None:
        raise ValueError(f"{NAME}: an approval is decided from outside any run")
    decider = await ctx.session.get(Principal, ctx.principal_id)
    if decider is None or decider.class_ not in DECIDERS:
        raise ValueError(f"{NAME}: a principal of class {DECIDERS} decides an approval")

    # The approval names the run, and the lock order is the run row first (the
    # lifecycle mutex, runs/MODULE.md): the peek is unlocked, and the locked
    # re-read below is what decides — two deciders serialize on the run row.
    peek = await ctx.session.get(Approval, args.approval_id)
    if peek is None:
        return {"decided": False, "state": None}
    await ctx.session.execute(
        select(Run.id).where(Run.id == peek.run_id).with_for_update()
    )
    approval = await ctx.session.get(
        Approval, args.approval_id, with_for_update=True, populate_existing=True
    )
    if approval is None or approval.state != "requested":
        return {"decided": False, "state": approval.state if approval else None}

    if args.decision == "approve":
        approval.state = "open"
        approval.granted_by = ctx.principal_id
    else:
        approval.state = "rejected"
        approval.reason = args.reason
    await ctx.session.flush()

    queued = await ctx.session.scalar(
        update(Run)
        .where(Run.id == approval.run_id, Run.state == "waiting_approval")
        .values(state="queued", updated_at=func.now())
        .returning(Run.id)
        .execution_options(synchronize_session=False)
    )
    if queued is not None:
        ctx.session.add(
            StepQueue(
                org_id=UUID(ctx.session.info["org"]),
                run_id=approval.run_id,
                step_no=approval.step_no,
                queue_tag=QUEUE_TAG,
            )
        )
        await ctx.session.flush()
    return {"decided": True, "state": approval.state, "run_queued": queued is not None}
