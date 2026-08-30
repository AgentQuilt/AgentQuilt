"""The surface an agent is talking through, as a prefix layer it does not own.

L4 is the surface contract: what streaming, intake and stopping mean where this
run is answering. It was a kernel constant until this module landed (owner,
2026-08-30); registering it here is what makes a second surface a module and not
a kernel edit. Importing this module registers the contributor, the same way
importing a module declares its operations.
"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.kernel.context.contributors import version
from app.kernel.context.service import register_prefix
from app.kernel.ports.context_contributor import Layer, PrefixSlot, Scope

# Fable-authored prompt text (AGENTS.md, Model routing); it is prompt wording,
# not a message to a person, and it changes only through that route.
WEB_THREAD_CONTRACT = (
    "Surface: a web chat thread. Your reply streams to the person as plain text;"
    " make it direct and complete. New messages can arrive between steps; they"
    " appear in your intake, oldest first, each tagged with its kind. To act,"
    " propose the declared operations you were given; a call that needs approval"
    " parks until a person answers, and you continue from its recorded result."
    " When you have nothing further to propose, answer and stop."
)


class WebSurfaceContributor:
    """L4, the web thread's contract. One surface, so the scope selects nothing."""

    owner = "surfaces"
    prefix_slots: tuple[PrefixSlot, ...] = ("L4",)

    async def fetch(self, session: AsyncSession, scope: Scope) -> str:
        return WEB_THREAD_CONTRACT

    def layers(self, source: str) -> tuple[Layer, ...]:
        return (Layer(slot="L4", version=version("web", source), body=source),)


register_prefix(WebSurfaceContributor())
