# PDP One — Deployment Agent

## Purpose

The Deployment Agent is the controlled operational bridge for deployment/health/backup actions on the Windows host. It uses a local signed-file queue rather than arbitrary shell access.

## Bootstrap live state — 2026-08-17

- configured: true
- queue available: true
- pending requests: 0
- completed responses: 268
- arbitrary shell allowed: false
- low disk space: false
- free bytes observed: 999,762,956,288

These are timestamped values and must be refreshed before a deployment.

## Exact deployment evidence

Deployment request `49dc7f7e-a978-41fc-a869-c8f7f5c1cefd` proves:

- deployment ID: `analysis-hyper-turbo-d2d70c67-20260812-r2`
- exact commit: `d2d70c67f5e1e3290a6a165b953118e4e7f90c9f`
- result: succeeded / healthy
- change-management mode: development-fast
- routine backup: skipped for that development-fast deployment

This evidence is distinct from GitHub `main` merge commit `b99dfedc...`.

## Request-id rule

Once a deployment write returns a Request ID, never issue a duplicate deploy because MCP/Connected App becomes temporarily unavailable during service restart. Poll the exact request until terminal state.

If a write fails before a Request ID is returned, first inspect queue/completed counters to determine whether it was accepted before retrying.

## Health

A deployment terminal success should be followed by appropriate independent health checks. Historical V23 evidence showed that generic health alone is not proof the intended frontend bundle/version is installed; version/build identity or behavior evidence may also be needed.

## Modes

### development_fast
Current normal development flow:

Branch → CI → immutable exact images → exact-commit deploy → short health → merge.

No automatic rollback. Routine backup/restore verification is not automatically required for non-destructive changes.

### standard / guarded
May use stronger preview/backup/restore/approval gates according to active policy and risk.

## Safety

The Agent must not be treated as a generic command shell. Volume prune/destructive storage operations, Rancher reset, WSL unregister and token rotation are outside normal deployment behavior and remain specially guarded.
