# runs

- Interface: `create(session, agent_definition, skill_version, *, stage) -> Run`, `send(session, run_id, text) -> MailboxMessage | None`, `events(session, run_id, after_cursor) -> Sequence[Event]` and `cancel(session, run_id) -> bool`. Plain functions inside the caller's transaction, reading the org and the principal off the session the way `declare.ledger` does; no port, since Postgres is the only dependency.
- Ceiling: `create` computes ADR-0015's capability ceiling once and stores it on the row, so a run cannot widen later. Phase 1's intersection is `identity.effective_grants` for the originator plus the definition's memory scope.
- Stage: ADR-0012's one predicate at run start — a PROD run refuses a skill version that is not PROD-stage, and the violation is a `ValueError`, not a denial, because nobody is asking permission yet.
- Mailbox: `send` allocates `seq` under `SELECT ... FOR UPDATE` on the run row, so two senders serialise instead of colliding on `uq_mailbox_message_run_seq`. That lock is also the tenancy proof: row-level security hides another org's run, so the lock finds nothing and the call returns `None` having written nothing.
- Events: `events` is the run's ledger stream ordered by `Event.id`, and that id is the cursor wave 9's SSE resumes from.
- Cancel: D4 in one transaction — `state = cancelled`, the run's `step_queue` rows deleted, its `requested` and `open` approvals expired, and a `run_journal` event `run.cancelled`. No new event kind, no new table.
- Mapped: `step_queue`, `mailbox_message` and `checkpoint`, column for column with migration 0001, on the store's `Base` so the drift test reads them; `core.run` stays mapped in `store/models.py` and is imported, never mapped twice.
- Not built: the claim, lease and step loop, `checkpoint` writes, mailbox drain, and the `work` and `tick` entry points — all wave 8 Part B. Also absent: child runs (`parent_id`), narrowing state, pinned workers and any queue tag other than `main`.
- Tests: `tests/test_runs.py`, against a real Postgres; the mailbox test uses two sessions on two connections, because the thing under test is a row lock.
