# PDP One — Delta Sync Protocol

## Purpose

A conversation that has already completed its initial `PDPONE START` Context Sync must **not reload the full Project Memory on every later instruction**.

Use a persistent per-conversation context baseline and refresh only deltas that could change the correctness or safety of the next action.

## 1. Conversation baseline

After the first successful activation in a conversation, remember at least:

- activation state = `ACTIVE`;
- baseline GitHub `main` SHA;
- Project Memory `schema_version` and `memory_version`;
- relevant canonical files/decision IDs already loaded;
- active PDP Session Issues and their last observed update/phase;
- open relevant PR numbers and head SHAs;
- current work Session Issue/branch/PR if one exists;
- relevant live Runtime identity/version/checkpoint if the current work depends on Runtime;
- relevant ChatGPT Automation logical IDs/spec versions/live `updated_at` if the current work depends on Automation.

This is a **conversation cache**, not a new system of record.

## 2. Lightweight check before later instructions

For each later instruction in the same activated conversation, first perform a cheap Change Detector appropriate to the requested action:

1. Read current GitHub `main` SHA.
2. Check open `[PDP SESSION]` Issues / active-work records for new or changed work.
3. Check open relevant PRs and their head SHAs.
4. If Runtime facts matter to the action, refresh only the relevant live Runtime status/version.
5. If Automation facts matter, refresh only the relevant live Automation status/spec version.

Do not reread the entire historical archive, all Session Logs, all domain documents, or all live sources merely because another user message arrived.

## 3. If nothing relevant changed

When the baseline is still valid:

- reuse the conversation's already-loaded canonical context;
- continue directly;
- do not perform a full memory reload;
- still apply ordinary safety checks specific to the requested operation.

## 4. If `main` changed

Compare the previous baseline SHA to current `main`.

Read only:

- changed commit/PR/session metadata;
- changed filenames;
- diffs or canonical documents that intersect the current work scope;
- new/changed decisions that affect the current scope;
- changed guardrail/governance files if any.

If the changes are unrelated to current scope, record that the baseline advanced and continue without loading unrelated domain history.

After reconciliation, advance the conversation baseline to the new `main` SHA.

## 5. If another chat changed unmerged work

If an active Session Issue or open PR changed while `main` did not:

- inspect the changed Issue heartbeat and PR head/changed filenames;
- compare soft-lock scope with the current conversation;
- load only overlapping or dependency-relevant changes;
- use Split, Sequence, Integrate, Rebase/Refresh, or explicit conflict acceptance when needed.

Unrelated in-progress work does not trigger a full Project Memory reload.

## 6. Mandatory checkpoints use Delta Sync

After initial activation, the required checkpoints are **delta checkpoints**, not full reloads:

- PRE-WRITE
- PRE-DEPLOY
- PRE-MERGE

Each checkpoint refreshes the minimum authoritative facts necessary for that risk boundary.

## 7. Full reload triggers

Perform a broader/full canonical reload only when one or more of these conditions applies:

- `PDP-ONE-START-HERE.md` or core governance semantics changed materially;
- Project Memory schema changed incompatibly;
- source-of-truth precedence or safety guardrails changed;
- a major architecture/domain redesign invalidates the cached context;
- the conversation baseline cannot be reliably reconciled from Git history/active-work records;
- a very large relevant change set makes selective reconciliation unsafe;
- the user explicitly requests a full resync/audit.

Even a full canonical reload does **not** mean reading raw historical archives unless they are relevant.

## 8. Runtime and Automation freshness

GitHub Delta Sync does not replace authoritative live verification.

- Runtime-sensitive writes refresh the relevant Server/PDP One live facts near the action.
- Automation-sensitive writes read both GitHub desired spec and the relevant live ChatGPT Automation near the action.
- Historical snapshots never substitute for live state.

## 9. Baseline report

A compact internal/visible report may use:

```text
PDP One Delta Sync
Conversation activation: ACTIVE
Previous main: <sha>
Current main: <sha>
Main delta: NONE / RELEVANT / UNRELATED
Active-session delta: NONE / RELEVANT / UNRELATED / CONFLICT
Relevant runtime delta: NONE / CHANGED / NOT REQUIRED / UNVERIFIED
Relevant automation delta: NONE / CHANGED / NOT REQUIRED / UNVERIFIED
Context action: REUSE / PATCH / BROADER RESYNC
Result: PASS / CONFLICT / INCOMPLETE
```

## 10. Core principle

**Load once, detect cheaply, patch selectively, reload broadly only when necessary.**