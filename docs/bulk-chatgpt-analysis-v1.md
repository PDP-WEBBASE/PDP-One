# Bulk ChatGPT Analysis v1

This implementation keeps analysis single-stage and model-driven while reducing transport and persistence overhead.

- Direct ChatGPT analysis for every claimed notice; no local rule-based pre-filter.
- Compact claim payload with empty fields omitted and Context carried once per batch.
- Batch limit increased to 500 records.
- Compact short-key result schema accepted by the existing import tool.
- Every result is persisted on the Run Item.
- Detailed AI Drafts are created only for recommended, urgent, ambiguous, needs-information, or score >= 60 items.
- Existing hash, claim-token, Context and human-review protections remain active.
- No contract, receivable, payment, opportunity, approval, or publication side effects.
