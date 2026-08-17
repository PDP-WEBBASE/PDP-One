# PDP ONE — START HERE

> **STOP — DO NOT MODIFY PDP ONE UNLESS THE USER HAS ACTIVATED `PDPONE START` AT THE BEGINNING OF THE REQUEST.**

This file is the mandatory entry point for every ChatGPT session, developer, recovery session, deployment session, automation-maintenance session, and project change affecting PDP One.

## Activation gate

Only `PDPONE START` at the beginning of the user's operational request activates change mode.

Without it, work is **READ-ONLY / ADVISORY**. Do not create branches, commits, PRs, server writes, database writes, deployments, recovery mutations, token rotations, or ChatGPT Automation changes.

`PDPONE STATUS` is read-only status/context sync. `PDPONE END` finalizes memory sync and closes the active session.

Activation does **not** bypass safety. Destructive recovery, token rotation, volume operations, or other specially guarded actions still require their own explicit authorization.

## Mandatory Context Sync after activation

Read and reconcile, in this order:

1. `docs/project-memory/MANIFEST.json`
2. `docs/project-memory/CURRENT_STATE.md`
3. `docs/project-memory/SYSTEM_OF_RECORD_MATRIX.md`
4. `docs/project-memory/live-sources/LIVE_SOURCE_REGISTRY.md`
5. `docs/project-memory/SECURITY_AND_SAFETY_GUARDRAILS.md`
6. `docs/project-memory/MULTI_CHAT_COORDINATION.md`
7. `docs/project-memory/CURRENT_BACKLOG.md`
8. `docs/project-memory/decisions/DECISION_REGISTER.md`
9. All open GitHub session Issues / active-work records
10. All open PRs
11. Latest relevant Session Logs
12. Domain documents relevant to the request
13. Relevant live sources: GitHub, PDP One Runtime/Server, and/or ChatGPT Automations

Do not substitute historical snapshots for live verification.

## Required status before write

Produce a short internal/visible sync report:

```text
PDP One Context Sync
Activation: PDPONE START
Canonical memory: PASS / INCOMPLETE
GitHub main: <sha>
Runtime: VERIFIED / NOT REQUIRED / UNVERIFIED
Automations: VERIFIED / NOT REQUIRED / UNVERIFIED
Active sessions: <n>
Open PRs: <n>
Relevant decisions: <ids>
Concurrency: CLEAR / OVERLAP
Result: PASS / CONFLICT / INCOMPLETE
```

Only `PASS` permits normal project writes. Resolve `CONFLICT`/`INCOMPLETE` first for risky changes.

## Multi-chat rule

Before the first write, create a PDP Session Issue that declares scope and soft-locks modules/files/database/runtime/automations. Refresh active sessions and `main` again at **PRE-WRITE, PRE-DEPLOY, and PRE-MERGE**.

If another chat overlaps, use Split, Sequence, Integrate, Rebase/Refresh, or explicit user-approved conflict acceptance. Never proceed blindly.

## Source-of-truth rule

- GitHub: source code, canonical memory, decisions, historical evidence, desired configuration and change coordination.
- PDP One Runtime/Server: live application, database, deployment-agent and operational state.
- ChatGPT Automations: live scheduled-task execution state.
- Historical transfer packages: immutable evidence of what was known at a particular time, **not current state**.

## Exact-version rule

Always keep these separate:

- GitHub `main`
- PR head commit
- merge commit
- deployed exact commit
- deployment ID
- image/build identity

Never infer deployed identity from a merge SHA.

## Definition of done

`Code done != Project done`.

A project change is complete only after implementation/verification, deployment evidence when applicable, canonical memory update, and session closure.

## Bootstrap prompt for future chats

> This session is operational only if the user's message begins with `PDPONE START`. After activation, read this file and all Mandatory Context. Refresh dynamic information from the authoritative live source. Check active GitHub sessions and open PRs before writing. Create a Session Issue and soft-lock scope. Repeat Context Sync at START, PRE-WRITE, PRE-DEPLOY and PRE-MERGE. Do not proceed through overlap without conflict resolution. Record decisions, scope changes, commits, CI, failures, deployments, health, automation changes and merges in the session record. Historical snapshots are not live truth, and GitHub merge SHA is not the deployed exact commit. Never store secrets in the repository. Only execute project changes when Context Sync is PASS.
