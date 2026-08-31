"""The web thread: start a run, steer it, watch its ledger stream.

The three routes are the person's half of `runs`; the agent's half is the `work`
role. Nothing here dispatches an operation — a thread is a run, and a run's calls
are made by the worker under the ceiling `create` stored.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterable
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Header, HTTPException, status
from fastapi.sse import EventSourceResponse, ServerSentEvent
from pydantic import BaseModel
from sqlalchemy import select

from app.kernel.runs.service import create, events, send
from app.kernel.store.models import AgentDefinition
from app.kernel.store.service import session
from app.serve import Scoped, Who

router = APIRouter()

# The stream polls the ledger for the same reason the roles do (ADR-0019), and a
# reader that has just connected reads its backlog before it waits at all.
STREAM_POLL_SECONDS = 1.0


class Message(BaseModel):
    text: str


class Thread(BaseModel):
    run_id: UUID


class Posted(BaseModel):
    seq: int


@router.post("/threads", status_code=status.HTTP_201_CREATED)
async def open_thread(db: Scoped) -> Thread:
    """Start a run on the org's agent definition; the person's thread is that run."""
    definition = (
        await db.scalars(
            select(AgentDefinition).order_by(AgentDefinition.version.desc()).limit(1)
        )
    ).one()
    return Thread(run_id=(await create(db, definition, None)).id)


@router.post("/runs/{run_id}/messages", status_code=status.HTTP_202_ACCEPTED)
async def steer_run(run_id: UUID, message: Message, db: Scoped) -> Posted:
    """One message into the run's mailbox; the next step drains it."""
    posted = await send(db, run_id, message.text)
    if posted is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "no such run")
    return Posted(seq=posted.seq)


@router.get("/runs/{run_id}/events", response_class=EventSourceResponse)
async def stream_events(
    run_id: UUID,
    who: Who,
    last_event_id: Annotated[int, Header(alias="Last-Event-ID")] = 0,
) -> AsyncIterable[ServerSentEvent]:
    """The run's ledger stream, resumed from the last event the client saw.

    The cursor is the ledger id the client sends back as `Last-Event-ID`, so a
    reconnect replays from there and repeats nothing. A run this org cannot see
    streams empty rather than 404: row-level security hides it, and so does this.
    """
    cursor = last_event_id
    while True:
        # A session per pass, so the reader sees what has committed since the
        # last one and holds no transaction open while it writes to the socket.
        async with session(who.org_id, who.principal_id) as db:
            batch = [
                (
                    event.id,
                    ServerSentEvent(
                        id=str(event.id),
                        event=event.kind,
                        data={"step_no": event.step_no, "payload": event.payload},
                    ),
                )
                for event in await events(db, run_id, cursor)
            ]
        for event_id, frame in batch:
            cursor = event_id
            yield frame
        await asyncio.sleep(STREAM_POLL_SECONDS)
