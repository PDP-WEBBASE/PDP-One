# PDP One Canonical Project Memory

This directory is the long-term project memory and governance control plane for PDP One.

## Purpose

It exists so that a future ChatGPT session can understand the project without depending on the private memory of an earlier chat, and so multiple chats can work on different areas without silently contradicting one another.

The memory has three layers:

1. **Historical sources and evidence** — what was known or observed at a given point in time.
2. **Canonical knowledge** — active decisions, architecture, business rules, lessons, backlog and current cached state.
3. **Live coordination** — active GitHub session records, open PRs, scope locks and live-source verification.

## Federated authority model

GitHub is not a raw replica of the server.

- **GitHub** is authoritative for source, project history, active decisions, desired configuration and change coordination.
- **PDP One Runtime/Server** is authoritative for live application/database/agent state.
- **ChatGPT Automations** are authoritative for the live scheduled tasks actually configured in ChatGPT.
- **Transfer packages** are historical evidence. Their snapshots must never be silently promoted to current state.

See `SYSTEM_OF_RECORD_MATRIX.md` and `live-sources/LIVE_SOURCE_REGISTRY.md`.

## Historical bootstrap sources

The initial migration includes:

- `PDPOne-Transfer-Package-v10.0-2026-07-31` — 69 files; ZIP SHA-256 `fac51cd0ee4999b53fcae613c0ca6186a7e3fdcb4e7f99f1c0e606b71a62fff4`.
- Historical imported context referenced by that package.
- GitHub evidence and PR history.
- Runtime/deployment evidence available through PDP One.
- ChatGPT Automation state.
- The current project chat, including the work that produced PR54, PR55, PR56, PR57, PR58, adaptive admission, `newest_first`, Hyper Turbo, eight-lane desired design, and the later `PDPONE START` governance decision.

The transfer package contains a summarized historical chronology rather than a complete line-by-line export of every old chat. That limitation is preserved in `GAPS_AND_UNVERIFIED.md`; missing transcript content must not be invented.

## Historical source integrity

The transfer ZIP was re-audited on 2026-08-17:

- ZIP file count: 69
- extracted file count: 69
- extracted bytes: 11,318,119
- internal `file-checksums.sha256`: 68/68 covered files PASS (the checksum manifest itself is not self-hashed)
- secret-like text scan: no recognized private-key/PAT/OpenAI-key/JWT/Bearer/credential-assignment pattern found in the textual files; normal security review still applies before preserving any new raw source.

## Current bootstrap status

The canonical-memory bootstrap is tracked by GitHub Issue #59 and branch `docs/project-memory-bootstrap-20260817`.

At bootstrap start:

- GitHub main: `b99dfedc43c64c00b536bcb625d62499d7f1a4c3`
- deployed exact commit verified by deployment report: `d2d70c67f5e1e3290a6a165b953118e4e7f90c9f`
- deployment ID: `analysis-hyper-turbo-d2d70c67-20260812-r2`
- PostgreSQL: connected
- contracts: 10
- receivables: 3
- analysis drafts: 1,219
- active analysis run: `755ad573-0bdd-4437-9b3e-0f6f09a64b96`
- run snapshot: total 51,632; completed 12,326; remaining 39,293
- analysis priority: `newest_first`
- adaptive admission: enabled
- deployment queue: available; pending 0; arbitrary shell disabled
- open PRs: #45 and #46, both old operational branches based on historical main states
- active PDP memory/session issues before bootstrap: none
- Automation drift discovered: Hyper Turbo lanes 1,2,4,6,7,8 enabled; lanes 3 and 5 disabled, despite the eight-lane historical desired configuration.

All numbers above are timestamped bootstrap observations, not permanent truths.

## Core files

- `../..//PDP-ONE-START-HERE.md` — mandatory activation/context protocol.
- `MANIFEST.json` — machine-readable entry map.
- `CURRENT_STATE.md` / `.json` — cached current view with source/freshness.
- `SYSTEM_OF_RECORD_MATRIX.md` — authority for each class of information.
- `live-sources/LIVE_SOURCE_REGISTRY.md` — how to refresh dynamic information.
- `SECURITY_AND_SAFETY_GUARDRAILS.md` — hard safety rules.
- `MULTI_CHAT_COORDINATION.md` — concurrent-session protocol.
- `decisions/DECISION_REGISTER.md` — active, historical and superseded decisions.
- `history/TIMELINE.md` — chronological evolution.
- `sources/SOURCE_CATALOG.md` — transfer/evidence provenance.
- `procurement/` — extraction, analysis and workflow knowledge.
- `automations/` — desired/live schedule governance and drift.

## Operating principle

**Append history; replace only the cached current view.**

A decision that changes is marked Superseded. A failed deployment remains Failed. A resolved incident remains in history. Current state is separately refreshed from live sources.
