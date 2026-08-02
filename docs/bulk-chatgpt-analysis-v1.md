# Bulk ChatGPT Analysis v1

This implementation keeps analysis single-stage and model-driven while reducing transport and persistence overhead.

- Direct ChatGPT analysis for every claimed notice; no local rule-based pre-filter.
- Compact claim payload with empty fields omitted and Context carried once per batch.
- Adaptive batch sizing supports up to 500 records while enforcing a compact payload-character budget.
- Compact short-key result schema is accepted by the existing import tool.
- Every result is persisted on the Run Item and remains valid for later runs when Context and Content Hash are unchanged.
- Detailed AI Drafts are created only for recommended, urgent, ambiguous, needs-information, or score >= 60 items.
- Existing hash, claim-token, Context and human-review protections remain active.
- The default bulk claim lease is one hour to avoid duplicate work during large ChatGPT batches.
- No contract, receivable, payment, opportunity, approval, or publication side effects.
