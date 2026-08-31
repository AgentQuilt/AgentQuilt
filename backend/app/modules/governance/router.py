"""The two things a person does from outside a run: answer a parked call, take
one back.

Both routes are their declaration's call rather than a second write path: the
grant check, the action and the ledger entry are dispatch's, and the route only
carries the path id and the body into the operation's args.
"""

from __future__ import annotations

from typing import Literal
from uuid import UUID, uuid4

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.kernel.declare.models import Json
from app.kernel.declare.registry import CallContext, registry
from app.kernel.declare.service import Call, Committed, Denied, dispatch
from app.kernel.identity.service import Caller
from app.modules.governance.service import NAME as DECIDE, UNDO
from app.serve import Scoped, Who

router = APIRouter()


class Decision(BaseModel):
    decision: Literal["approve", "reject"]
    reason: str | None = None


@router.post("/approvals/{approval_id}/decide")
async def decide(
    approval_id: UUID, decision: Decision, db: Scoped, who: Who
) -> Json:
    return await _call(
        db, who, DECIDE, {"approval_id": str(approval_id), **decision.model_dump()}
    )


@router.post("/actions/{action_id}/undo")
async def undo(action_id: UUID, db: Scoped, who: Who) -> Json:
    return await _call(db, who, UNDO, {"action_id": str(action_id)})


async def _call(
    db: AsyncSession, who: Caller, operation_name: str, args: Json
) -> Json:
    """A run-less call: a decision comes from outside every run, so it carries no
    ceiling and no continuation, and dispatch refuses it rather than parking it."""
    outcome = await dispatch(
        CallContext(
            session=db,
            principal_id=who.principal_id,
            run_id=None,
            step_no=None,
            registry=registry,
        ),
        Call(
            operation_name=operation_name,
            args=args,
            tool_call_id=str(uuid4()),
        ),
    )
    if isinstance(outcome, Denied):
        raise HTTPException(status.HTTP_403_FORBIDDEN, outcome.reason)
    if not isinstance(outcome, Committed):
        # The tool call id is fresh per request, so nothing replays, and a call
        # with no run to park in is denied above rather than left waiting.
        raise RuntimeError(f"{operation_name}: unreachable outcome {outcome}")
    return outcome.result
