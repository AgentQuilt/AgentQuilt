# model

- Interface: `run(session, assembled, run_row, *, runner) -> Answered | Refused`, and the `ModelRunner` port (`ports/model_runner.py`): `run(assembled, binding) -> Completion`, with `Binding`, `ProposedCall` and `Usage` as frozen value types.
- Budget: the cap is checked before the call, because spent tokens cannot be returned; a refusal is a ledger `denial(budget_exceeded)` carrying spent, estimate and cap. The worker's failed-run handling is wave 8, deliberately absent here.
- Adapters: `PydanticAIModelRunner`, provider-generic — the tier binding's provider string selects the Pydantic AI provider at runtime, nothing outside the adapter names one; the test kit's `FakeModelRunner` runs on `FunctionModel` with `ALLOW_MODEL_REQUESTS = False`.
- Cache: ADR-0014's mandatory position is recorded on the manifest (`prefix_end_tokens`) for every provider and handed only to a provider with a cache API, which the generic request path is not.
- Mapped: `tier_binding` and `usage_record`, column for column with migration 0001; the executor binding row is seeded idempotently (openrouter, z-ai/glm-5.3-flash).
- Not built: cost-based budgets, retries, streaming, further cache positions, and any second provider named in code.
- Tests: `tests/test_model.py` at head; the OpenRouter smoke test runs only when the key is set.
