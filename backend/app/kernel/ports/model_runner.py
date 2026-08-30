"""The seam between an assembled turn and whoever answers it.

One method, so a runner cannot grow a second way in. The prompt arrives already
assembled (ADR-0006: slot order and the tool block are kernel-owned), and the
binding arrives as three strings, so no provider is named outside the adapter
that reaches one.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from app.kernel.context.service import AssembledTurn
from app.kernel.store.models import Json


@dataclass(frozen=True, slots=True)
class Binding:
    """A tier binding's three terms, as `core.tier_binding` stores them."""

    provider: str
    model: str
    effort: str | None


@dataclass(frozen=True, slots=True)
class ProposedCall:
    """A tool call the model proposed; `declare.dispatch` decides whether it runs."""

    name: str
    args: Json
    tool_call_id: str


@dataclass(frozen=True, slots=True)
class Usage:
    """What the call cost, in the three counts `core.usage_record` keeps."""

    input_tokens: int
    output_tokens: int
    cached_tokens: int


@dataclass(frozen=True, slots=True)
class Completion:
    """One model answer: its text, the calls it proposed, its cost, its caching.

    `cache` is whatever the provider reported about the prefix cache, recorded in
    the manifest as it came; an empty mapping means the provider said nothing.
    """

    text: str
    calls: tuple[ProposedCall, ...]
    usage: Usage
    cache: Json


class ModelRunner(Protocol):
    """The port. A runner renders the turn its provider's way and answers."""

    async def run(self, assembled: AssembledTurn, binding: Binding) -> Completion: ...
