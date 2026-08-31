"""A toy module the kernel does not ship: three operations over one table.

Dispatch needs something to dispatch, and the kernel has no modules of its own yet.
The table lives in `mod_test`, created here rather than in the migration chain, so
nothing a test needs ever reaches the schema the product ships. Its row-level
security is written the way migration 0001 writes every tenant table's, because a
toy that skips it would prove dispatch works only where nothing is enforced.
"""

from __future__ import annotations

from uuid import UUID, uuid4

from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from app.kernel.declare.models import Json
from app.kernel.declare.registry import CallContext, Declares, Registry

_ORG = "current_setting('app.org_id', true)::uuid"
_SCHEMA = (
    "CREATE SCHEMA IF NOT EXISTS mod_test",
    "GRANT USAGE ON SCHEMA mod_test TO agentquilt_app",
    "CREATE TABLE IF NOT EXISTS mod_test.note ("
    " id uuid PRIMARY KEY, org_id uuid NOT NULL, body text NOT NULL)",
    "ALTER TABLE mod_test.note ENABLE ROW LEVEL SECURITY",
    "ALTER TABLE mod_test.note FORCE ROW LEVEL SECURITY",
    "DROP POLICY IF EXISTS rls_note ON mod_test.note",
    "CREATE POLICY rls_note ON mod_test.note FOR ALL TO agentquilt_app"
    f" USING (org_id = {_ORG}) WITH CHECK (org_id = {_ORG})",
    "GRANT ALL ON mod_test.note TO agentquilt_app",
)
# An upsert, not an insert: dispatch runs the body before it checks the version,
# so an operation that cannot run twice would fail at the primary key instead of
# reaching the conflict the savepoint exists to roll back.
_WRITE = text(
    "INSERT INTO mod_test.note (id, org_id, body) VALUES (:id, :org, :body)"
    " ON CONFLICT (id) DO UPDATE SET body = EXCLUDED.body"
)
_DELETE = text("DELETE FROM mod_test.note WHERE id = :id")
_SELECT = text("SELECT body FROM mod_test.note ORDER BY body")
# A replace, not an insert: `effective_grants` reads one level per operation, and
# `seed` already grants its undoable operation, so a second row for the same pair
# would leave which level applies to row order.
_UNGRANT = text(
    'DELETE FROM core."grant" WHERE principal_id = :principal'
    " AND operation_name = :name"
)
_GRANT = text(
    'INSERT INTO core."grant" (id, org_id, principal_id, operation_name, level)'
    " VALUES (:id, :org, :principal, :name, :level)"
)


class NoteWrite(BaseModel):
    note_id: UUID
    body: str


class NoteRemove(BaseModel):
    note_id: UUID


class NoteList(BaseModel):
    pass


async def note_table(url: str) -> None:
    """Create `mod_test.note` idempotently, as the container's superuser."""
    engine = create_async_engine(url)
    async with engine.begin() as connection:
        for statement in _SCHEMA:
            await connection.execute(text(statement))
    await engine.dispose()


async def write_note(ctx: CallContext, args: NoteWrite) -> Json:
    """Write one note."""
    await ctx.session.execute(
        _WRITE,
        {"id": args.note_id, "org": UUID(ctx.session.info["org"]), "body": args.body},
    )
    return {"note_id": str(args.note_id)}


async def remove_note(ctx: CallContext, args: NoteRemove) -> Json:
    """Remove one note; this is what compensates a write."""
    await ctx.session.execute(_DELETE, {"id": args.note_id})
    return {"note_id": str(args.note_id)}


async def list_notes(ctx: CallContext, args: NoteList) -> Json:
    """List the notes this org can see."""
    bodies = await ctx.session.scalars(_SELECT)
    return {"bodies": list(bodies)}


def notes_registry() -> Registry:
    """A registry of its own, so the process registry stays what `catalog` renders.

    Declared by calling the decorator rather than applying it: a fresh registry per
    test module is the point, and a decorator can only bind to one.
    """
    registry = Registry()
    # `write_note`, not `write`: a name is `module.verb_noun` and the registry
    # rejects a verb with no noun (naming-conventions.md, Operations).
    registry.operation(
        "note.write_note",
        Declares(
            mode="write",
            reversal="reversible",
            compensator="note.remove_note",
            aggregate=("note", "note_id"),
        ),
    )(write_note)
    registry.operation(
        "note.remove_note",
        Declares(mode="write", reversal="irreversible", aggregate=("note", "note_id")),
    )(remove_note)
    registry.operation("note.list_notes", Declares(mode="read"))(list_notes)
    return registry


async def grant(
    session: AsyncSession, principal_id: UUID, operation_name: str, level: str
) -> None:
    """This principal's one grant row for the operation, read back by
    `identity.effective_grants`."""
    await session.execute(
        _UNGRANT, {"principal": principal_id, "name": operation_name}
    )
    await session.execute(
        _GRANT,
        {
            "id": uuid4(),
            "org": UUID(session.info["org"]),
            "principal": principal_id,
            "name": operation_name,
            "level": level,
        },
    )
