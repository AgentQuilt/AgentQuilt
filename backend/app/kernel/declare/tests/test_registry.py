"""What the registry refuses at decoration time, and that the page on disk agrees.

Nothing here touches the database: a declaration is data, and its checks run before
a process is far enough along to have one.
"""

from __future__ import annotations

import importlib

import pytest
from pydantic import BaseModel

from app.kernel.declare.catalog import PAGE, render
from app.kernel.declare.models import Json
from app.kernel.declare.registry import CallContext, Declares, Handler, Registry
from app.kernel.declare.registry import registry as process_registry


class Args(BaseModel):
    body: str


async def _write(ctx: CallContext, args: Args) -> Json:
    """Write a thing."""
    return {"body": args.body}


async def _write_differently(ctx: CallContext, args: Args) -> Json:
    """Write a thing, but describe it differently."""
    return {"body": args.body}


def _declare(name: str, declares: Declares, fn: Handler = _write) -> Registry:
    """A registry of exactly one operation, or the ValueError that stopped it."""
    registry = Registry()
    registry.operation(name, declares)(fn)
    return registry


def test_catalog_is_fresh() -> None:
    importlib.import_module("app.modules")
    assert PAGE.read_text() == render(process_registry)


def test_inline_declaration_name_shape_rejected() -> None:
    with pytest.raises(ValueError, match="naming-conventions"):
        _declare("Note.Write", Declares(mode="write", reversal="irreversible"))


def test_read_with_write_verb_rejected() -> None:
    with pytest.raises(ValueError, match="naming-conventions"):
        _declare("note.write_note", Declares(mode="read"))


def test_reversible_requires_compensator() -> None:
    with pytest.raises(ValueError, match="naming-conventions"):
        _declare("note.write_note", Declares(mode="write", reversal="reversible"))


def test_version_id_is_content_addressed() -> None:
    declares = Declares(mode="write", reversal="irreversible")
    ids: list[str] = []
    for fn in (_write, _write, _write_differently):
        registry = _declare("note.write_note", declares, fn)
        ids.append(registry.version_id(registry.get("note.write_note")))
    assert ids[0] == ids[1]
    assert ids[0] != ids[2]


def test_duplicate_name_rejected_at_registration() -> None:
    registry = Registry()
    write = Declares(mode="write", reversal="irreversible")
    first = registry.operation("note.write_note", write)
    second = registry.operation("note.write_note", write)

    first(_write)
    with pytest.raises(ValueError, match="declared twice"):
        second(_write)


def test_sync_function_rejected() -> None:
    def handler(ctx: CallContext, args: Args) -> Json:
        raise NotImplementedError

    declares = Declares(mode="write", reversal="irreversible")
    with pytest.raises(TypeError, match="async"):
        Registry().operation("note.write_note", declares)(handler)
