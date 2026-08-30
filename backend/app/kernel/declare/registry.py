"""What a module declares, and what the kernel is allowed to call.

A declaration is data before it is a call path: `declaration()` renders it,
`version_id()` content-addresses that rendering, and `publish()` writes one row per
operation so an action can point at the exact declaration it ran under. Names and
classes are checked when the decorator runs, so a wrong shape is a startup error
and never a runtime surprise, which is what naming-conventions.md asks for.
"""

from __future__ import annotations

import hashlib
import inspect
import json
import re
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any, Literal, get_type_hints
from uuid import UUID

from pydantic import BaseModel
from pydantic_ai import ToolDefinition
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.kernel.declare.models import Json, OperationVersion

Mode = Literal["read", "write"]
Reversal = Literal["reversible", "draftable", "irreversible"]
Stage = Literal["DEV", "QA", "PROD"]
Taint = Literal["web_fetch", "untrusted_file", "inbound_external_message"]

_NAME = re.compile(r"^[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*$")
_READ_VERBS = ("get_", "list_", "search_")
_SEE = "see naming-conventions.md, Operations, events, skills"


@dataclass(frozen=True, slots=True)
class CallContext:
    """What an operation's body may reach; here, so nothing imports back."""

    session: AsyncSession
    principal_id: UUID
    run_id: UUID | None
    step_no: int | None
    registry: Registry


# The second parameter is the operation's own args model; `Any` is what lets a
# concrete `(CallContext, NoteWrite)` function satisfy this.
Handler = Callable[[CallContext, Any], Awaitable[Json]]


@dataclass(frozen=True, slots=True)
class Declares:
    """What a module states about one operation; the rest is read off the function."""

    mode: Mode
    reversal: Reversal | None = None
    compensator: str | None = None
    aggregate: tuple[str, str] | None = None
    stage: Stage = "DEV"
    taint: Taint | None = None


@dataclass(frozen=True, slots=True)
class Operation:
    """One declared operation, as the registry holds it."""

    name: str
    mode: Mode
    reversal: Reversal | None
    compensator: str | None
    aggregate: tuple[str, str] | None
    stage: Stage
    taint: Taint | None
    args_model: type[BaseModel]
    fn: Handler
    description: str


class Registry:
    """One process's operations. The kernel's own tests each build their own."""

    def __init__(self) -> None:
        self._operations: dict[str, Operation] = {}

    def operation[H: Handler](self, name: str, declares: Declares) -> Callable[[H], H]:
        _validate(name, declares)
        if name in self._operations:
            raise ValueError(f"operation {name!r} is declared twice; {_SEE}")

        def register(fn: H) -> H:
            doc = inspect.getdoc(fn) or ""
            self._operations[name] = Operation(
                name=name,
                mode=declares.mode,
                reversal=declares.reversal,
                compensator=declares.compensator,
                aggregate=declares.aggregate,
                stage=declares.stage,
                taint=declares.taint,
                args_model=_args_model(name, fn),
                fn=fn,
                description=doc.splitlines()[0] if doc else "",
            )
            return fn

        return register

    def get(self, name: str) -> Operation:
        return self._operations[name]

    def operations(self) -> list[Operation]:
        return sorted(self._operations.values(), key=lambda op: op.name)

    def declaration(self, op: Operation) -> Json:
        """What a caller needs to decide about the operation without calling it."""
        return {
            "name": op.name,
            "mode": op.mode,
            "reversal": op.reversal,
            "compensator": op.compensator,
            "aggregate": list(op.aggregate) if op.aggregate is not None else None,
            "stage": op.stage,
            "taint": op.taint,
            "description": op.description,
            "args_schema": op.args_model.model_json_schema(),
        }

    def version_id(self, op: Operation) -> str:
        canonical = json.dumps(
            self.declaration(op), sort_keys=True, separators=(",", ":")
        )
        return hashlib.sha256(canonical.encode()).hexdigest()

    async def publish(self, session: AsyncSession) -> None:
        """One row per operation; the table is global, so a re-run is a no-op."""
        for op in self.operations():
            await session.execute(
                insert(OperationVersion)
                .values(
                    id=self.version_id(op),
                    operation_name=op.name,
                    stage=op.stage,
                    declaration=self.declaration(op),
                )
                .on_conflict_do_nothing(index_elements=[OperationVersion.id])
            )

    def tool_definitions(self) -> list[ToolDefinition]:
        return [
            ToolDefinition(
                name=op.name,
                description=op.description,
                parameters_json_schema=op.args_model.model_json_schema(),
            )
            for op in self.operations()
        ]


def _validate(name: str, declares: Declares) -> None:
    verb = name.partition(".")[2]
    if not _NAME.match(name) or "_" not in verb:
        raise ValueError(f"operation name {name!r} is not module.verb_noun; {_SEE}")
    if verb.startswith(_READ_VERBS) != (declares.mode == "read"):
        raise ValueError(
            f"operation {name!r}: a read's verb starts with get_, list_ or search_"
            f" and a write's does not; {_SEE}"
        )
    _validate_reversal(name, declares)


def _validate_reversal(name: str, declares: Declares) -> None:
    if (declares.reversal is None) != (declares.mode == "read"):
        raise ValueError(
            f"operation {name!r}: a write declares a reversal class and a read"
            f" declares none; {_SEE}"
        )
    if (declares.compensator is None) != (declares.reversal != "reversible"):
        raise ValueError(
            f"operation {name!r}: a reversible operation names a compensator and no"
            f" other class may; {_SEE}"
        )


def _args_model(name: str, fn: Handler) -> type[BaseModel]:
    parameters = list(inspect.signature(fn).parameters)
    if len(parameters) != 2:
        raise TypeError(f"operation {name!r} must take (ctx, args), not {parameters}")
    annotation = get_type_hints(fn).get(parameters[1])
    if not (isinstance(annotation, type) and issubclass(annotation, BaseModel)):
        raise TypeError(
            f"operation {name!r}: parameter {parameters[1]!r} must be annotated with"
            f" a BaseModel subclass, not {annotation!r}"
        )
    return annotation


# The process's registry: what `agentquilt catalog` renders and dispatch reads.
registry = Registry()
