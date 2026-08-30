"""One model call against a real Postgres: the cap, the fake, the real provider.

The cap is the interesting half. A run that would go over it must leave a denial
and no usage row, because a usage row is a bill and nothing was bought; the fake
covers the other half, that a proposed tool call survives the round trip through
the adapter in the shape `declare.dispatch` takes.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from uuid import UUID, uuid4

import pytest
from pydantic import BaseModel
from pydantic_ai import models
from pydantic_ai.messages import (
    ModelMessage,
    ModelResponse,
    TextPart,
    ToolCallPart,
)
from pydantic_ai.models.function import AgentInfo
from sqlalchemy import select

from app.kernel.context.models import ContextManifest
from app.kernel.context.service import AssembledTurn, Call, assemble, tokens
from app.kernel.declare.models import Json
from app.kernel.declare.registry import CallContext, Declares, Registry
from app.kernel.identity.models import Grant
from app.kernel.model import service as model
from app.kernel.model.adapter import PydanticAIModelRunner
from app.kernel.model.models import UsageRecord
from app.kernel.ports.model_runner import ModelRunner
from app.kernel.store.models import AgentDefinition, Principal, Run
from app.kernel.store.service import session
from tests.kit import FakeModelRunner, two_principals

pytestmark = pytest.mark.anyio

OPERATION = "note.write_note"
NOTE = "We land on the higher price."
KEY_VAR = "OPENROUTER_API_KEY"
CALL = Call(
    provider="openrouter",
    model="z-ai/glm-5.3-flash",
    effort=None,
    budget_tokens=200_000,
    intake="Write the note about where we landed on pricing.",
)


class Args(BaseModel):
    body: str


async def _write_note(ctx: CallContext, args: Args) -> Json:
    """Write a note."""
    return {"body": args.body}


def _proposes(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
    """What a model does when the tool block offers the operation it needs."""
    return ModelResponse(
        parts=[
            TextPart("Writing that down."),
            ToolCallPart(OPERATION, {"body": NOTE}, tool_call_id="call-1"),
        ]
    )


def _never(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
    raise AssertionError("the runner was reached past a refused budget check")


@dataclass(frozen=True, slots=True)
class Setup:
    org_id: UUID
    principal_id: UUID
    agent_definition_id: UUID


@pytest.fixture(scope="module")
async def setup(migrated_url: str) -> Setup:
    """One org, its user principal granted the one operation the model is offered."""
    (org_id, system_id), _ = await two_principals(migrated_url)
    async with session(org_id, system_id) as scoped:
        agent_id = (await scoped.scalars(select(AgentDefinition.id))).one()
        principal_id = (
            await scoped.scalars(
                select(Principal.id).where(Principal.class_ == "user")
            )
        ).one()
        scoped.add(
            Grant(
                id=uuid4(),
                org_id=org_id,
                principal_id=principal_id,
                operation_name=OPERATION,
                level="may_use",
                scope_ref=None,
            )
        )
        await scoped.commit()
    return Setup(org_id, principal_id, agent_id)


async def _run_row(setup: Setup, budget_cap_tokens: int) -> Run:
    run = Run(
        id=uuid4(),
        org_id=setup.org_id,
        agent_definition_id=setup.agent_definition_id,
        skill_version_id=None,
        stage="DEV",
        state="running",
        budget_cap_tokens=budget_cap_tokens,
        prefix_key="",
        capability_ceiling={},
        prefix_profile="personal",
    )
    async with session(setup.org_id, setup.principal_id) as scoped:
        scoped.add(run)
        await scoped.commit()
    return run


async def _turn(setup: Setup, run: Run) -> AssembledTurn:
    """The prompt: one operation in the tool block, the intake in the envelope."""
    registry = Registry()
    registry.operation(OPERATION, Declares(mode="write", reversal="irreversible"))(
        _write_note
    )
    async with session(setup.org_id, setup.principal_id) as scoped:
        assembled = await assemble(scoped, run, step_no=1, call=CALL, registry=registry)
        await scoped.commit()
    return assembled


async def _answer(
    setup: Setup, assembled: AssembledTurn, run: Run, runner: ModelRunner
) -> model.Outcome:
    async with session(setup.org_id, setup.principal_id) as scoped:
        outcome = await model.run(scoped, assembled, run, runner=runner)
        await scoped.commit()
    return outcome


async def _usage(setup: Setup, run: Run) -> list[UsageRecord]:
    async with session(setup.org_id, setup.principal_id) as scoped:
        return list(
            await scoped.scalars(
                select(UsageRecord).where(UsageRecord.run_id == run.id)
            )
        )


async def test_budget_cap_denies(setup: Setup) -> None:
    run = await _run_row(setup, budget_cap_tokens=1)
    assembled = await _turn(setup, run)
    outcome = await _answer(setup, assembled, run, FakeModelRunner(_never))
    assert isinstance(outcome, model.Refused)
    assert outcome.reason == "budget_exceeded"
    assert outcome.event.kind == "denial"
    assert outcome.event.payload["reason"] == "budget_exceeded"
    assert outcome.event.payload["estimated_tokens"] == assembled.token_cost
    assert await _usage(setup, run) == []


async def test_fake_model_proposes_action(setup: Setup) -> None:
    run = await _run_row(setup, budget_cap_tokens=200_000)
    assembled = await _turn(setup, run)
    outcome = await _answer(setup, assembled, run, FakeModelRunner(_proposes))
    assert isinstance(outcome, model.Answered)
    call = outcome.completion.calls[0]
    assert (call.name, call.args) == (OPERATION, {"body": NOTE})
    # The name dispatch would look up is the one the tool block offered.
    assert call.name in next(
        layer.body for layer in assembled.prefix if layer.slot == "L5"
    )
    (usage,) = await _usage(setup, run)
    assert usage.tier == "executor"
    assert usage.input_tokens == outcome.completion.usage.input_tokens
    assert usage.output_tokens == outcome.completion.usage.output_tokens
    async with session(setup.org_id, setup.principal_id) as scoped:
        manifest = await scoped.get_one(ContextManifest, assembled.manifest_id)
    # The cache position is where the prefix ends, so it plus the envelope is
    # the whole prompt the manifest costed.
    envelope = sum(tokens(part.body) for part in assembled.envelope)
    position = manifest.cache_positions["prefix_end_tokens"]
    assert position == assembled.token_cost - envelope


@pytest.mark.skipif(
    os.getenv(KEY_VAR) is None, reason=f"{KEY_VAR} is not set in this environment"
)
async def test_openrouter_answers(
    setup: Setup, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The seeded binding, the real provider, one answer. Costs money; opt in."""
    monkeypatch.setattr(models, "ALLOW_MODEL_REQUESTS", True)
    run = await _run_row(setup, budget_cap_tokens=200_000)
    assembled = await _turn(setup, run)
    outcome = await _answer(setup, assembled, run, PydanticAIModelRunner())
    assert isinstance(outcome, model.Answered)
    assert outcome.completion.text or outcome.completion.calls
    (usage,) = await _usage(setup, run)
    assert usage.input_tokens > 0
