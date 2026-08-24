# Patterns to catch on your own diff

One example per line. `REVIEW.md` decides what blocks and what is an observation; this
file exists so you see it first. Where the two disagree, `REVIEW.md` wins.

## Blocks the review (P1 in REVIEW.md)

- Three or more files for a simple feature: a new `schemas.py`, `service.py` and `router.py` for one endpoint that reads a row.
- A new pattern for a one-off: a `Strategy` protocol with a single implementation.
- "Future flexibility": a `backend: str = "postgres"` parameter with one backend.
- A helper with one call site: `def _build_query(...)` called once, three lines above.
- A class with no instance state: `class UserService` whose methods take `session` as an argument.
- reuse-before-create unmet: a new part where an existing one composes or extends, or one created without the closest existing part named in the change description.
- one-adapter-seam: a port with one adapter, or a port around a pure function or an in-process dependency.
- deletion-test failed: `services/user_service.py` that forwards every call to `crud.py`.
- tests-past-interface: asserting on a private helper's return value.

## Gets an observation (P2 in REVIEW.md)

- Manager, Handler or Service proliferation: `UserManager` next to `UserHandler` next to `UserService`.
- Config for constants: `MAX_RETRIES = settings.max_retries` where nothing ever sets it.
- Middleware for a linear flow: a `@before_request` hook that could be one line in the route.
- try/except around a call that should propagate: `except Exception: return None` in a service function.
- A backward-compat shim where the code could just change: `def old_name(*a, **k): return new_name(*a, **k)`.

## What only you will catch (no lint, no reviewer line)

- Generic names: `data`, `result`, `temp`, `item`, `value`, `obj`, `info` outside a three-line scope. Name what it holds: `parsed_invoice`, `matching_rows`.
- Vague verbs in names: `handle_data`, `process_items`, `manage_users`. Say the action and the object.
- Comments that restate the code: `# increment the counter` above `counter += 1`; banner blocks like `# ---- INIT ----`. Comment the why, or nothing.
- The same shape everywhere: a docstring on every function including trivial ones, identical try/except in every route, the same five-line preamble in every module. Uniformity is the tell.
- Symmetric filler: three bullets, three options or three examples where the material has two or four; a decorative section that exists to complete a pattern.
- Placeholder content: lorem ipsum, "Your text here", `foo`/`bar` fixtures, sample rows invented to fill a table.
- Inflated line count: the diff grows by scaffold, re-exports, `__init__` boilerplate or docstrings on trivial functions, not by the change. Ten lines of fix beat a hundred of frame.
- Happy-talk: "robust", "comprehensive", "clean" in a comment, commit message or report. State what changed and what it does not handle.
- Poor locality: a function that reads three fields of another module's object to compute what that module should expose. Move the computation next to the data; in Python that is a module function beside it, not a new class.

## Already caught by the gates: spend no attention here

ruff: `except Exception` (`BLE001`), bare `except:` (`E722`), `pass` in an except (`S110`), `print` (`T201`), magic numbers (`PLR2004`), TODO without author or link (`TD002`, `TD003`), unused imports (`F401`), commented-out code (`ERA001`; inside `select = ["ALL"]`, confirm it stays selected when `pyproject.toml` lands), argument and complexity budgets (`PLR09xx`, `C901`).
Biome and tsc: `any` (`noExplicitAny`), nested ternaries, default exports, enums and namespaces (`erasableSyntaxOnly`), function length and parameter count.

If a gate is red, fix the code. `# noqa` is closed; a `pyproject.toml` change is a reviewable diff.
