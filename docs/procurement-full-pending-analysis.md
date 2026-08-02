# PDP One Procurement Full-Pending Analysis

## Purpose

PDP One no longer treats 20, 50, 12,900, a date range, or an old export as the definition of an analysis job. The source of truth is PostgreSQL at the moment a run is initialized.

A notice is eligible when it has no valid analysis for the current notice Content Hash and the active Analysis Context, or when it failed, was returned for revision, changed after analysis, or was explicitly selected for reanalysis.

## Run types

- `full_pending_analysis`: discovers every currently eligible notice and persists the complete queue.
- `incremental_analysis`: uses the same engine after the initial queue is empty. It processes new, changed, failed and returned notices.

Only one persistent run may be active. Manual and scheduled triggers therefore cannot analyze the same notice concurrently.

## Lifecycle

1. Create or reuse the active run.
2. Freeze the active Context ID, version and hash on the run.
3. Scan the full eligible PostgreSQL queryset without a fixed record cap.
4. Persist one `ProcurementAnalysisRunItem` per eligible notice.
5. Atomically claim items with a worker ID, UUID lease token and expiry.
6. Screen and deeply analyze the claimed package.
7. Import results through the official endpoint.
8. Validate Run Item, Notice ID, Content Hash, Context Hash and Claim Token.
9. Save only `NoticeAnalysisDraft` rows with `review_status=ai_draft`.
10. Continue until the persisted queue reports zero remaining items.

A scheduled invocation is only a dispatcher and monitor. It resumes an open run and does not impose an hourly limit on the internal run.

## Safety

The persistent analysis flow never automatically:

- approves or publishes an AI draft;
- selects an opportunity;
- records a participation decision;
- creates a contract, receivable or payment receipt;
- deletes a notice or previous analysis;
- changes the active Context, Prompt, keywords, qualifications or experience;
- deletes or prunes a Docker volume.

Every run, dataset and import is audited. Healthy imported drafts survive pause, cancellation and continuation.

## Dataset files

A dataset is stored under `/data/private/procurement-analysis/<dataset-id>/` and contains:

- `PDP-One-Procurement-Full-<dataset-id>.sql.gz`
- sharded `PDP-One-Procurement-AI-Input-<dataset-id>-part-XXXX.jsonl.gz`
- `PDP-One-Procurement-AI-Review-<dataset-id>.csv.gz`
- `PDP-One-Procurement-AI-Manifest-<dataset-id>.json`

The SQL export includes only `procurement_*` PostgreSQL tables. Authentication, sessions, tokens, cookies, private connection settings and unrelated finance tables are excluded. The manifest records SHA-256, file sizes, Context, migration head, run checkpoint and the isolated restore attempt result.

## Manual analysis continuation capsule

ChatGPT cannot be treated as the background worker. The PostgreSQL run and checkpoint are authoritative. If a controlling chat approaches a length, tool-call, timeout or context limit, use the following capsule in a new chat:

```text
PDP Manual Analysis Continuation
Run ID: <run-id>
Export ID: <dataset-id or none>
Import ID: <last-import-id or none>
Context ID: <context-id>
Context Hash: <context-hash>
Last Checkpoint: <checkpoint JSON>
Initial Queue: <count>
Processed: <count>
Remaining: <count>
Current Shard: <number>
Errors: <summary>
Next action: read the run status through PDP One - 04; do not create a new run; claim or import only from the saved checkpoint.
```

Suggested chat names:

- `PDP Manual Analysis – <date-time> – <run-id>`
- `PDP Manual Analysis Continuation – <run-id> – Part <n>`

Automatic creation of a separate ChatGPT conversation is not assumed. When the client does not expose an official chat-creation action, the user opens a new chat and pastes the generated capsule. The PDP One run continues independently of that chat.

## Development workflow

Until the owner exactly declares `پیاده سازی سامانه تکمیل شده است`, changes use:

`Branch → CI → Deploy exact commit → Short Health Check → Merge`

Routine approval, per-change backup, restore verification, local code snapshot, automatic rollback and heavy preview are disabled for ordinary changes. A destructive migration or sensitive database change must use the dedicated backup and restore path.
