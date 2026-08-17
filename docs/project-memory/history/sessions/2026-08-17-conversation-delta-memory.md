# PDP Session — Conversation Activation, Delta Sync and Memory Compaction

Session ID: `PDP-SESSION-20260817-CONVERSATION-DELTA-MEMORY`  
Issue: #72  
Date: 2026-08-17  
Starting main: `be268574fac4a8786664426535f57ce3003f9a35`  
Branch: `docs/conversation-delta-memory-20260817`

## User decisions

The user approved four governance changes:

1. `PDPONE START` is required once per new ChatGPT Conversation, not before every later change in the same Conversation.
2. Define a tiny bootstrap so a fresh chat knows what `PDPONE START` means and which GitHub repository/file to read.
3. Use Delta Sync for later instructions in the same Conversation instead of reloading full Project Memory repeatedly.
4. Add Memory Retention & Compaction with tiered memory, lazy loading, compact topical summaries, and no routine storage of raw high-volume data/logs in normal Git history.

## Concurrency / Delta Sync

At START/PRE-WRITE:

- GitHub `main` = `be268574fac4a8786664426535f57ce3003f9a35`.
- Active Session #61 / PR66: MCP end-to-end stability hardening.
- Active Session #68 / PR67: analysis retry backpressure/statistics.
- Exact changed-file inspection found no file-level overlap with this governance session.
- Resolution: **Split**. This session touches only activation/bootstrap/delta-sync/retention governance files and does not modify PR66/PR67 files, Runtime, database or Automations.

A later Delta Check before PR confirmed `main` had not changed.

## Implemented governance

### Conversation-scoped activation

- `PDPONE START` activates PDP One once per Conversation after successful initial Context Sync.
- Later requests in the same Conversation do not need the keyword again.
- Closing one Work Session/PR does not deactivate the Conversation.
- `PDPONE END` explicitly deactivates mutation mode for that Conversation after applicable closure/sync.

Decision: DEC-037.

### Minimal fresh-chat bootstrap

Added `PDP-ONE-CHATGPT-BOOTSTRAP.md` with the minimal product-level instruction:

- recognize `PDPONE START`;
- open `PDP-WEBBASE/PDP-One`;
- read `PDP-ONE-START-HERE.md`;
- keep activation for the same Conversation;
- rely on GitHub/live source governance rather than duplicating history.

Decision: DEC-038.

Important limitation: the available tools in this Session expose no write action for ChatGPT Project Instructions. The bootstrap is therefore **defined in GitHub but product-level installation is not programmatically verified**. The memory explicitly forbids claiming otherwise.

### Delta Sync

Added `docs/project-memory/coordination/DELTA_SYNC_PROTOCOL.md`.

Core rule:

`Load once → detect cheaply → patch selectively → reload broadly only when necessary.`

The Conversation baseline tracks `main`, memory version, active sessions/PR heads and only relevant Runtime/Automation versions. Later PRE-WRITE/PRE-DEPLOY/PRE-MERGE checks are Delta Sync checkpoints.

Decision: DEC-039.

### Memory Retention & Compaction

Added `docs/project-memory/MEMORY_RETENTION_AND_COMPACTION.md` with:

- Tier 0 bootstrap/routing;
- Tier 1 active operational context;
- Tier 2 domain summaries;
- Tier 3 detailed history;
- Tier 4 source/evidence archives;
- lazy loading for deeper tiers;
- no routine Git accumulation of DB dumps, repetitive raw logs, routine Automation payloads, Docker/runtime data or large backups;
- compact Session Logs that reference exact evidence instead of copying large payloads;
- topical summary compaction while preserving audit history/provenance.

Decision: DEC-040.

## Files changed

- `PDP-ONE-CHATGPT-BOOTSTRAP.md`
- `PDP-ONE-START-HERE.md`
- `docs/project-memory/MANIFEST.json`
- `docs/project-memory/CHANGE_PROTOCOL.md`
- `docs/project-memory/MULTI_CHAT_COORDINATION.md`
- `docs/project-memory/MEMORY_RETENTION_AND_COMPACTION.md`
- `docs/project-memory/coordination/DELTA_SYNC_PROTOCOL.md`
- `docs/project-memory/decisions/DECISION_REGISTER.md`
- this Session Log

## Runtime/application impact

None.

- No application code changed.
- No database change/migration.
- No Server/Deployment Agent mutation.
- No ChatGPT Automation mutation.
- No token/Tailscale/Docker/WSL/Rancher action.
- Application deployment is not required for this documentation/governance-only change.

## Definition-of-done plan

- Open governance PR from this branch.
- Require Project Memory/CI validation on exact final head.
- Run PRE-MERGE Delta/Concurrency Sync.
- Merge only if no new overlap/conflict is introduced.
- Close Issue #72 after merge.

Product-level ChatGPT Project Instruction installation remains a separately verifiable product-setting step because no write tool for that setting is available in this Session.