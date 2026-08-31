# Kernel modules

The six kernel modules and their interfaces. One line each until the wave that builds it lands.

## store

interface: `session(org_id, principal_id)`, wave 2. schema: 0001, wave 1.

## identity

interface: `resolve`, `effective_grants`, `args_hash`, approvals, wave 5; `resolve` takes a bearer token and no session, wave 9.

## declare

interface: registry, `dispatch()`, ledger `commit()` and `append()`, wave 4.

## runs

interface: `create`, `send`, `post`, `events`, `cancel`, wave 8; `claim` / `step` / `work_once` (the `work` role) and `tick_once` (the `tick` role), wave 8; the web thread's three routes, wave 9.

## context

interface: not built yet, wave 7.

## model

interface: not built yet, wave 7.
