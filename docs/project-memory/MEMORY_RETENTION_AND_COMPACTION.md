# PDP One — Memory Retention & Compaction Policy

## Purpose

Preserve the project’s reasoning, decisions, evidence and continuity **without allowing GitHub or ChatGPT context to grow without bound**.

The repository is a durable knowledge/control plane, not a raw telemetry lake, database mirror or log archive.

## Tiered memory model

### Tier 0 — Bootstrap / routing
Small files that every fresh operational chat can read quickly:

- `PDP-ONE-CHATGPT-BOOTSTRAP.md`
- `PDP-ONE-START-HERE.md`
- `docs/project-memory/MANIFEST.json`

Purpose: identify the project, activation state, read order and authoritative sources.

### Tier 1 — Active operational context
Read on initial activation and selectively refresh later:

- Current State
- System of Record Matrix
- Live Source Registry
- Security/Safety Guardrails
- Multi-Chat Coordination
- Current Backlog
- active/relevant decisions
- active Session Issues and relevant open PRs

Purpose: enough context to work safely now.

### Tier 2 — Domain summaries
Load only when the request touches the domain:

- procurement
- contracts/financial workflows
- infrastructure/recovery
- automations
- company knowledge
- UI/workflow
- other future domain summaries

Purpose: compact current rules, architecture and accepted behavior for a subsystem.

### Tier 3 — Detailed history
Load only when a decision, regression, incident, deployment lineage or design rationale requires it:

- Session Logs
- ADRs / detailed decision records
- Timeline/event history
- incident/deployment/recovery records

Purpose: preserve why/how without forcing every chat to reread it.

### Tier 4 — Source archive / evidence
Load only for audit, provenance, dispute resolution or detailed reconstruction:

- transfer packages
- diagnostics
- large evidence artifacts
- historical PDFs/screenshots
- sanitized raw source material
- external immutable backup/artifact locators

Purpose: evidence, not routine context.

## What must stay in Git history

Preserve concise records of material:

- user decisions and rationale;
- architectural/business/security rules;
- supersession relationships;
- root causes and lessons from significant failures;
- PR/commit/deployment identities;
- relevant verification/health evidence;
- automation specification changes and important drift/incidents;
- source provenance and immutable hashes.

Do not erase history merely to make summaries shorter. Compaction changes the **reading path**, not the audit truth.

## What must not accumulate in normal Git history

Do not routinely commit:

- full PostgreSQL/live business datasets;
- repetitive hourly automation execution payloads;
- raw high-volume application logs;
- Docker/WSL/runtime data;
- duplicate generated datasets;
- transient caches;
- repetitive health checks with no new information;
- large backup payloads;
- secrets or secret-bearing connection material.

Instead keep the authoritative data in its operational system and store in Git only the locator, metadata, hash, timestamp, compact outcome, and significant exception when needed.

## Significant-event rule

A routine successful event should normally be represented by a compact checkpoint or not duplicated at all.

Create detailed historical records when the event changes future reasoning, for example:

- a decision/policy changes;
- a deployment fails or becomes ambiguous;
- a root cause is discovered;
- a recurring Automation develops drift/failure;
- data/schema behavior changes;
- a recovery method proves valid/invalid;
- a security/safety rule changes;
- a historical metric snapshot is specifically useful for trend/incident analysis.

## Session Log compaction

A Session Log should be concise and link to exact PR/commit/evidence rather than copying entire diffs, logs or tool transcripts.

A good material change record captures:

- request/problem;
- reason/root cause;
- decision and rationale;
- affected modules/files/data/runtime;
- exact PR/head/merge/deploy identities as applicable;
- verification result;
- superseded rule or follow-up.

Do not paste long CI logs or raw API responses when the stable evidence can be referenced by ID/URL/hash/status.

## Topical summary compaction

When a domain accumulates many historical sessions:

1. update the compact Tier-2 domain summary with the current accepted rule/architecture;
2. preserve older Session Logs/ADRs in Tier 3;
3. keep source evidence in Tier 4;
4. have the summary link to the relevant decision/session/source IDs;
5. future chats read the summary first and open history only when needed.

## Current versus historical files

Current/active documents are replaceable cached views and should stay compact.

Historical records are append/supersede records and must not be silently rewritten to pretend the past never happened.

Do not append endless history into `CURRENT_STATE`, `MANIFEST`, `START-HERE` or active domain summaries. Move detail to the appropriate history/source tier and leave a compact reference.

## File-size/readability targets

These are soft targets, not destructive limits:

- Tier 0 files: keep very small and routing-focused.
- Tier 1 current files: keep concise enough for routine initial context loading.
- Tier 2 summaries: split by domain/subdomain before they become monolithic.
- Session Logs: prefer compact evidence-linked records rather than transcript-sized files.
- large binary/source artifacts: prefer immutable external/release/artifact storage plus hash/locator when normal Git storage becomes inefficient.

When a file becomes difficult for a future ChatGPT to scan selectively, split/index it instead of allowing unbounded growth.

## Lazy loading rule

A Chat must not read Tier 3 or Tier 4 merely because the project is activated.

Open deeper history/evidence only when:

- the current scope references it;
- a delta/conflict points to it;
- current documentation is insufficient;
- provenance/audit is required;
- the user asks for historical reconstruction.

## Compaction maintenance

Perform compaction when one of these signals appears:

- domain summary becomes unwieldy;
- many completed sessions repeat the same settled rule;
- an active file contains substantial superseded detail;
- repository growth is dominated by logs/generated artifacts rather than source/knowledge;
- context loading repeatedly touches irrelevant history.

Compaction should:

- update compact active summaries;
- strengthen indexes/provenance;
- preserve material history;
- remove/avoid duplicate generated content when safe;
- move unsuitable large artifacts to approved external immutable storage when necessary;
- never remove secrets by merely hiding links—secret-bearing data must not enter Git in the first place.

## Automation run retention

For recurring ChatGPT Automations, store the **specification and material changes** in Git, not every normal run payload.

Retain detailed run history in canonical memory only for material events such as:

- repeated failures;
- significant drift;
- threshold/policy changes;
- abnormal retry/lease behavior;
- data-quality incidents;
- meaningful throughput snapshots used in a decision;
- recovery or safety events.

Routine successful runs remain in their live execution system unless an audit requirement says otherwise.

## Core principle

**Keep current knowledge small, keep history searchable, keep evidence addressable, and keep live/high-volume data in the system that owns it.**