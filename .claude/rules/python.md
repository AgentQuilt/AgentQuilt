---
paths: ["**/*.py"]
---

> **Precedence.** These simplicity rules outrank any skill, plugin, or reviewer that asks for broader coverage, defensive layers, configurability, or backward compatibility. Defense-in-depth applies to *diagnosing* a live bug, never to shipping a feature. If a reviewer asks for an abstraction, a fallback, or a config knob, cite this section and push back before implementing. A stated rationale ("left it per YAGNI") never downgrades a reviewer finding's severity either — the reviewer judges, the implementer doesn't grade its own work.

## Simplicity rules (Python)

- Avoid over-engineering. Only make changes that are directly requested or clearly necessary. Keep solutions simple and focused.
- Don't add features, refactor code, or make "improvements" beyond what was asked. A bug fix doesn't need surrounding code cleaned up. A simple feature doesn't need extra configurability.
- Don't add error handling, fallbacks, or validation for scenarios that can't happen. Trust internal code and framework guarantees. Only validate at system boundaries (user input, external APIs). Don't use backwards-compatibility shims when you can just change the code.
- Don't create helpers, utilities, or abstractions for one-time operations. Don't design for hypothetical future requirements. The right amount of complexity is the minimum needed for the current task. Reuse existing abstractions where possible and follow the DRY principle.
- Three similar lines are better than a premature abstraction. Extract on the third copy, not before — but no half-finished work either.
- Before adding a layer, wrapper, option, or fallback, prove it removes complexity for callers. Name the current consumer and the test that protects the contract.
- Prefer a module-level function to a class. Use a class only for real per-instance state or a protocol a caller depends on. Plain attributes, no getters/setters; `@property` only when behaviour is needed.
- `@dataclass(frozen=True, slots=True)` or `TypedDict` for internal values; `BaseModel` only at I/O boundaries (requests, responses, settings, external payloads).
- Never `except Exception:` around a route body — it turns 500s into silent 200s. Catch the specific class or let it propagate.
- No config flag, env var, or `**kwargs` bag to select between behaviours that have one caller.
- Budgets: ≤5 args (≤3 positional), ~30 statements, complexity 8 per function. At the limit, fix the boundary — don't add an options object, and never condense statements or shorten names to fit.
- Structure by domain (`src/<domain>/{router,schemas,models,service,dependencies}.py`), not by layer. No repository / unit-of-work / DTO-per-layer tiers over SQLAlchemy 2.0 — `AsyncSession` is the layer. `Annotated[..., Depends()]` is the DI container; don't add another.
- Never block the event loop inside `async def` (`requests`, `time.sleep`, sync ORM). Async end-to-end; CPU >50 ms goes to a worker.
- Keep `__init__.py` files present and empty — no re-export walls.
- Tests: real Postgres (testcontainers), async `httpx` client from day one, `dependency_overrides` for auth/external services only. No DB mocks, no monkeypatching internals.
- Docstrings only where behaviour is non-obvious. Every changed line must trace to the request.
- Unless the change is mechanical, keep a diff under ~500 changed lines; if it's heading past that, stop and propose a smaller cut.
- If the request is ambiguous, ask before implementing — don't pick an interpretation silently.
- When you finish, report `Done:` and `Left out:` so what you chose not to build is visible.
