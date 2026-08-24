---
paths: ["**/*.ts", "**/*.tsx"]
---

> **Precedence.** These simplicity rules outrank any skill, plugin, or reviewer that asks for broader coverage, defensive layers, configurability, or backward compatibility. Defense-in-depth applies to *diagnosing* a live bug, never to shipping a feature. If a reviewer asks for an abstraction, a fallback, or a config knob, cite this section and push back before implementing. A stated rationale ("left it per YAGNI") never downgrades a reviewer finding's severity either — the reviewer judges, the implementer doesn't grade its own work.

## Simplicity rules (TypeScript)

- Avoid over-engineering. Only make changes that are directly requested or clearly necessary. Keep solutions simple and focused.
- Don't add features, refactor code, or make "improvements" beyond what was asked. A bug fix doesn't need surrounding code cleaned up. A simple feature doesn't need extra configurability.
- Don't add error handling, fallbacks, or validation for scenarios that can't happen. Trust internal code and framework guarantees. Only validate at system boundaries (user input, external APIs).
- Don't create helpers, utilities, or abstractions for one-time operations. Don't design for hypothetical future requirements. Reuse existing abstractions where possible.
- Three similar lines are better than a premature abstraction. Extract on the third copy, not before — but no half-finished work either.
- Apply the deletion test: if deleting a module makes complexity vanish, it was a pass-through — delete it. One adapter is a hypothetical seam; two is a real one.
- Don't create a helper or wrapper referenced from only one call site.
- No classes unless you need instance state or a framework demands one. No DI containers, no service/repository layers, no Result wrapper around calls that already throw usefully.
- No enums (`erasableSyntaxOnly` makes them a build error) — use `as const` objects. No namespaces, no parameter properties.
- `type` by default; `interface extends` when modelling inheritance. No default exports unless the framework requires one. No barrel files re-exporting a subtree.
- `readonly` properties by default. Prefer `userId: string | undefined` to `userId?: string`. Model variant shapes as discriminated unions, never a bag of optionals.
- `any` only inside generic function bodies, never at a module boundary. Top-level `import type`. Explicit return types on exported functions (not JSX components).
- Budgets: cognitive complexity ≤10, ≤60 lines per function, ≤3 parameters, ≤300 lines per file. A wide interface is a design signal — fix the boundary, don't add an options bag, and never condense statements, strip JSDoc, or shorten names to fit.
- No new dependency without one sentence on why Node 24 core can't do it (`parseArgs`, `styleText`, `--env-file`, `fetch`, `fs.glob`, `node:sqlite`, `node:test`, `structuredClone`, `crypto.randomUUID`, `AbortSignal.timeout` are built in).
- React: no `useEffect` for derived data or event handling — Effects only synchronise with external systems; the React Compiler handles memoisation (`useMemo`/`useCallback` are escape hatches, not defaults).
- JSDoc only when behaviour is not self-evident. Install packages with the install command, never by editing package.json from memory.
- Unless the change is mechanical, keep a diff under ~500 changed lines; if it's heading past that, stop and propose a smaller cut.
- If the request is ambiguous, ask before implementing.
- When you finish, report `Done:` and `Left out:`.
