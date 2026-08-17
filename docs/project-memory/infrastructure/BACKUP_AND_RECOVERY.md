# PDP One — Backup and Recovery Memory

This document preserves historical backup/recovery evidence and current safety policy. It does not contain backup passphrases or credentials.

## Historical verified backups from Transfer v10

### BKP-001 — V25 final backup
- Name: `PDP-One-final-Backup-20260725-003429`
- Historical association: V25 operational deployment lineage.
- Source: `backup-register.csv`, V25 baseline.

### BKP-002 — Post-release final backup
- Name: `PDP-One-final-Backup-20260725-075733`
- Historical association: release/stabilization period.

### BKP-003 — Portable encrypted backup
- Name: `PDP-One-Portable-Backup-20260721-223550.pdpone`
- Historical result: portable backup workflow verified, including isolated restore/copy hash checks.
- Important: portable encrypted payload itself was intentionally not embedded in the transfer ZIP.
- Never store its secret/passphrase in GitHub.

### BKP-004 — User external/local archive path
- Historical path: `D:\BackUp PDP-0NE-14050429-01`
- Purpose: retain an external copy the user can move to another physical disk.
- Path should be verified on the current Windows host before relying on it.

### Historical stable baseline backup
- `PDP-One-final-Backup-20260720-172949`
- Associated with BACKLOG-001 / stable deployment `cf1bcc40...` and isolated restore verification.

## Historical recovery lessons

Transfer/history records show several generations of startup/recovery behavior:

1. Early manual CONNECT-CHATGPT/startup concepts.
2. Stable Startup scheduled-task/self-heal model.
3. Diagnostics for Nginx/API/session/build-ID, Docker/Rancher, DNS, Tailscale/Funnel and MCP.
4. V23 taught that a healthy endpoint can still serve an old bundle; recovery verification must prove intended version/build, not only HTTP health.
5. Disk cleanup/WSL compaction must not prune Docker volumes.
6. Later exact-image/development-fast architecture reduced the need for heavyweight routine per-commit backup/restore gates for non-destructive development changes.

A recovery procedure that was correct historically must not be rerun blindly if the current startup/deployment architecture has superseded it.

## Current recovery modes

### Development-fast failure recovery
- No automatic rollback.
- Diagnose exact accepted deployment request/report.
- If recovery is required, redeploy an explicitly known previous exact GitHub commit through the controlled deployment mechanism.
- Do not claim an automatic rollback occurred.

### Standard/guarded recovery
Historical guarded workflows may use:
- verified final backup
- isolated restore verification
- approved deployment/rollback path

Use this only when current change-management mode/risk requires it or the user explicitly requests standard-mode rollback.

## Hard prohibitions

Do not use recovery as justification for:

- Rancher Factory Reset
- WSL unregister
- VHDX deletion
- Docker volume prune
- PostgreSQL/private-files volume deletion
- blind Tailscale identity reset
- MCP token rotation without explicit user instruction

## Backup system of record

- Backup binary/payload: approved Windows/external storage.
- Backup metadata/history: canonical GitHub memory + runtime reports.
- Current backup availability: verify live before restore.
- A filename in historical docs does not prove the file still exists today.

## Verification requirements

A backup should only be described as verified when the relevant evidence says so. Preserve:

- creation result
- source version/deployment
- database/archive integrity checks
- isolated restore result where applicable
- file/hash/copy verification where applicable
- storage location
- timestamp

Do not retroactively label historical unverified backups as verified.
