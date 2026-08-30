# governance

- Interface: one declared operation, `governance.decide_approval(approval_id, decision, reason)`, dispatched like any other write. It is unversioned on purpose: approvals are not a versioned aggregate, so the declaration names no `aggregate` (ADR-0017 allows none) and a caller passes no `expected_version`.
- Decision: only a `requested` approval moves; anything else returns `{"decided": false, "state": ...}` and still commits its own action, because the ledger records that the answer was given. Approve moves it to `open` with `granted_by` set to the deciding principal; reject moves it to `rejected` and stores the reason, which becomes the tool result when the parked call resumes.
- Decider: a principal of class `user` or `system` (ADR-0004). Anything else raises, and dispatch surfaces the raise as the tool failing; a denial event for it waits for the wave that gives modules a refusal path.
- Continuation: in the same transaction, a guarded `update(Run)` from `waiting_approval` to `queued` returning the id, and the `StepQueue` row for `(run_id, step_no)` only when that returned a row. A run that is absent, cancelled or already queued is decided and not enqueued (`run_queued` is false).
- Not built: `undo(action)` (wave 9), any read of the approval queue, and expiring an approval (wave 8's tick).
