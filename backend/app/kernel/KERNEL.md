# Kernel modules

The six kernel modules and their interfaces, on one page. Each module's `MODULE.md`
carries the rules behind its interface; `FROZEN.md` states what a change to any of
them costs. Nothing outside `kernel/` may be imported from inside it.

## store

`session(org_id, environment_id, principal_id)` — the only way into the database, an
async context manager whose transaction sets the (org, environment, principal) scope;
`engine()`; `tenants()` — every such triple a background role acts as; `seed()` — two
demo orgs, each with its dev and prod planes, a user, a token, an agent definition and
the executor tier binding.

## identity

`resolve(token) -> Caller | None` — the one read serve makes before it has a scope;
`effective_grants(session, principal_id) -> Mapping[name, level]`;
`args_hash(operation_version_id, args, scope) -> str`;
`consume_approval(session, Consume) -> UUID | None` and
`park_approval(session, Park) -> Approval | Decided`.

## declare

`registry.operation(name, Declares)` — how a module declares an operation;
`dispatch(ctx, Call) -> Committed | Replayed | Denied | WaitingApproval` — the one
way one runs; under it `commit(session, Commit) -> Action` and
`append(session, Append) -> Event`, the only writers of `core.event` and
`core.action`; `registry.publish(session)` and `catalog.render(registry)`, which
writes `app/OPERATIONS.md`.

## context

`assemble(session, run, step_no, *, call, registry) -> AssembledTurn` — the prefix,
the envelope, `prefix_key` and one persisted manifest per model call;
`tokens(body)`, the one tokenizer; `register_prefix(contributor)`, how a module
takes a layer. The two contracts are `ports/context_contributor.py` (ADR-0027).

## model

`run(session, assembled, run_row, *, runner) -> Answered | Refused` — the budget
check before the call, the provider through the port, the usage row and the cache
telemetry after it. The port is `ports/model_runner.py`; its adapters are
`PydanticAIModelRunner` and the test kit's `FakeModelRunner`.

## runs

`create` / `send` / `post` / `events` / `cancel` for what a person does to a run,
and the three web-thread routes over them (`router.py`);
`claim` / `step` / `work_once(scope, *, worker_id, runner, registry, clock)` for the
`work` role, and `tick_once(scope, *, clock)` for the `tick` leader. The run row is
the lifecycle mutex; the lock order is in `MODULE.md`.
