# declare

- Interface: `commit(session, Commit) -> Action` and `append(session, Append) -> Event`, both inside the caller's transaction, both reading the org from the session; the ledger is the only writer of `event` and `action`.
- Role: each switches the connection to `agentquilt_ledger_writer` for its statements and back to `agentquilt_app` before returning, because the app role may only read the ledger.
- Raises: `VersionConflict(expected, actual)` when `expected_version` does not match `stream_head`; a repeated idempotency key returns the stored `Action` and writes nothing, and a concurrent first use of one raises the primary key's `IntegrityError`.
- Mapped: `event`, `stream_head`, `operation_version`, `action`, `idempotency_key`, column for column with migrations 0001 and 0002; the deferred `fk_event_action` is what lets one transaction write the event and its action in that order.
- Not built: the operation registry and dispatch (wave 4), `approval_id` (wave 5, identity), compensation, and any read model over the ledger.
