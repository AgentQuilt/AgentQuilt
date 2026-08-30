"""Assembly: one prompt per model call, one `prefix_key`, one manifest row.

Slot order, the tool block and the key are kernel-owned (ADR-0006, ADR-0014): a
contributor hands over layers and slices and never sees where they land. L0 and L5
never cross the seam (ADR-0013), and L4 is a constant here until `modules/surfaces`
registers the real contract (owner, 2026-08-30).
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, cast
from uuid import UUID, uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from app.kernel.context.contributors import (
    InstructionsContributor,
    SkillsContributor,
    version,
)
from app.kernel.context.models import ContextManifest
from app.kernel.declare.models import Json
from app.kernel.declare.registry import Registry
from app.kernel.identity.service import effective_grants
from app.kernel.ports.context_contributor import (
    EnvelopeContributor,
    PrefixContributor,
    PrefixProfile,
    Scope,
    Slice,
    Turn,
)
from app.kernel.store.models import Run

# The one surface Phase 1 serves; `surfaces` (wave 9) replaces both this and the
# L4 text below with a registered contributor.
SURFACE = "web"
# PLACEHOLDER, L0 and L4: prompt-layer wording is written in a Fable pass
# (AGENTS.md, Model routing), so these two carry a marker and not their text.
PLATFORM_POLICY = "PLACEHOLDER: platform policy (L0)."
WEB_SURFACE_CONTRACT = "PLACEHOLDER: web surface contract (L4)."

_KERNEL = "kernel"
_PREFIX_ORDER = ("L0", "L1", "L2", "L3", "L4", "L5", "L6")
_ENVELOPE_ORDER = ("D1", "D3", "D4", "D5", "D6")
# The levels that put an operation in front of the model at all.
_USABLE = ("may_use", "asks_first")

_skills = SkillsContributor()
_PREFIX: tuple[PrefixContributor[Any], ...] = (InstructionsContributor(), _skills)
_ENVELOPE: tuple[EnvelopeContributor, ...] = (_skills,)


@dataclass(frozen=True, slots=True)
class Call:
    """What the caller knows and the run row does not carry.

    The tier binding's three terms are part of prefix identity (ADR-0014) and
    `model` owns the row they come from; `budget_tokens` is the prompt budget the
    envelope is dropped against; `intake` is this turn's message, until `surfaces`
    owns D6.
    """

    provider: str
    model: str
    effort: str | None
    budget_tokens: int
    intake: str


@dataclass(frozen=True, slots=True)
class PrefixLayer:
    """One layer as assembly holds it: a contributor's `Layer` with its owner
    attached, or one of the kernel's own L0, L4 and L5."""

    slot: str
    owner: str
    version: str
    body: str


@dataclass(frozen=True, slots=True)
class AssembledTurn:
    """The prompt for one model call, and the manifest row that records it."""

    prefix: tuple[PrefixLayer, ...]
    envelope: tuple[Slice, ...]
    prefix_key: str
    token_cost: int
    manifest_id: UUID


def tokens(body: str) -> int:
    """A character estimate, until the `model` adapter brings a real tokenizer."""
    return (len(body) + 3) // 4


async def assemble(
    session: AsyncSession,
    run: Run,
    step_no: int,
    *,
    call: Call,
    registry: Registry,
) -> AssembledTurn:
    """Assemble one turn: prefix L0-L6, envelope by priority, manifest row."""
    scope = Scope(
        agent_definition_id=run.agent_definition_id,
        principal_id=UUID(session.info["principal"]),
        prefix_profile=cast("PrefixProfile", run.prefix_profile),
        surface=SURFACE,
    )
    grants = await effective_grants(session, scope.principal_id)
    prefix = await _prefix(session, scope, grants, registry)
    prefix_tokens = sum(tokens(layer.body) for layer in prefix)
    turn = Turn(run_id=run.id, step_no=step_no)
    kept, dropped = _fit(
        await _envelope(session, scope, turn, call.intake),
        prefix_tokens,
        call.budget_tokens,
    )
    token_cost = prefix_tokens + sum(tokens(part.body) for part in kept)
    manifest = ContextManifest(
        id=uuid4(),
        org_id=UUID(session.info["org"]),
        run_id=run.id,
        step_no=step_no,
        prefix_key=_prefix_key(prefix, call),
        layers=_manifest_layers(prefix, kept, dropped),
        token_cost=token_cost,
        # ADR-0014's mandatory position and the provider's cache telemetry are
        # the `model` adapter's to fill.
        cache_positions={},
        telemetry={},
        effective_scope=_effective_scope(scope, grants),
    )
    session.add(manifest)
    await session.flush()
    return AssembledTurn(
        prefix=prefix,
        envelope=kept,
        prefix_key=manifest.prefix_key,
        token_cost=token_cost,
        manifest_id=manifest.id,
    )


async def _prefix(
    session: AsyncSession,
    scope: Scope,
    grants: Mapping[str, str],
    registry: Registry,
) -> tuple[PrefixLayer, ...]:
    layers = [
        PrefixLayer("L0", _KERNEL, version("policy", PLATFORM_POLICY), PLATFORM_POLICY),
        PrefixLayer(
            "L4",
            _KERNEL,
            version(SURFACE, WEB_SURFACE_CONTRACT),
            WEB_SURFACE_CONTRACT,
        ),
        _tools(registry, grants),
    ]
    for contributor in _PREFIX:
        source = await contributor.fetch(session, scope)
        layers += [
            PrefixLayer(layer.slot, contributor.owner, layer.version, layer.body)
            for layer in contributor.layers(source)
        ]
    return tuple(sorted(layers, key=lambda layer: _PREFIX_ORDER.index(layer.slot)))


def _tools(registry: Registry, grants: Mapping[str, str]) -> PrefixLayer:
    """L5. An operation the principal may not use is not in the block at all, so
    the model never proposes a call that dispatch would only refuse."""
    usable = [
        {
            "name": tool.name,
            "description": tool.description,
            "parameters": tool.parameters_json_schema,
        }
        for tool in registry.tool_definitions()
        if grants.get(tool.name) in _USABLE
    ]
    body = json.dumps(usable, sort_keys=True, separators=(",", ":"))
    # ADR-0014 names the tool-schema hash as its own term in the key; it is L5's
    # version, so the ordered layer sequence below already carries it.
    return PrefixLayer("L5", _KERNEL, version("tools", body), body)


def _prefix_key(prefix: tuple[PrefixLayer, ...], call: Call) -> str:
    """ADR-0014: the ordered (slot, owner, version) sequence plus the tier binding.

    Effort is rendered into the prompt by both providers, so a binding that
    differs in any of the three is a different prefix and must not share a key.
    """
    terms = [f"{layer.slot}|{layer.owner}|{layer.version}" for layer in prefix]
    terms += [call.provider, call.model, call.effort or ""]
    return hashlib.sha256("\n".join(terms).encode()).hexdigest()


async def _envelope(
    session: AsyncSession, scope: Scope, turn: Turn, intake: str
) -> tuple[Slice, ...]:
    """D6 is the kernel's until `surfaces` owns it; D5, the mailbox drain, is the
    worker's (wave 8) and has no rows to read in Phase 1."""
    slices = [
        Slice(slot="D6", body=intake, provenance=f"{SURFACE}:intake", priority=0)
    ]
    for contributor in _ENVELOPE:
        slices += await contributor.slices(session, scope, turn)
    return tuple(slices)


def _fit(
    slices: tuple[Slice, ...], prefix_tokens: int, budget: int
) -> tuple[tuple[Slice, ...], tuple[Slice, ...]]:
    """Drop whole envelope slices, lowest priority number kept first, until the
    turn fits. A prefix layer is never dropped and no body is ever truncated."""
    kept: list[Slice] = []
    dropped: list[Slice] = []
    total = prefix_tokens
    for contribution in sorted(slices, key=lambda one: one.priority):
        cost = tokens(contribution.body)
        if total + cost > budget:
            dropped.append(contribution)
            continue
        kept.append(contribution)
        total += cost
    ordered = sorted(kept, key=lambda one: _ENVELOPE_ORDER.index(one.slot))
    return tuple(ordered), tuple(dropped)


def _manifest_layers(
    prefix: tuple[PrefixLayer, ...],
    kept: tuple[Slice, ...],
    dropped: tuple[Slice, ...],
) -> Json:
    """What the prompt was made of, including what was dropped to make it fit."""
    return {
        "prefix": [
            {
                "slot": layer.slot,
                "owner": layer.owner,
                "version": layer.version,
                "tokens": tokens(layer.body),
            }
            for layer in prefix
        ],
        "envelope": [
            {
                "slot": contribution.slot,
                "provenance": contribution.provenance,
                "priority": contribution.priority,
                "tokens": tokens(contribution.body),
                "kept": keep,
            }
            for slices, keep in ((kept, True), (dropped, False))
            for contribution in slices
        ],
    }


def _effective_scope(scope: Scope, grants: Mapping[str, str]) -> Json:
    return {
        "principal_id": str(scope.principal_id),
        "agent_definition_id": str(scope.agent_definition_id),
        "prefix_profile": scope.prefix_profile,
        "surface": scope.surface,
        "grants": dict(grants),
    }
