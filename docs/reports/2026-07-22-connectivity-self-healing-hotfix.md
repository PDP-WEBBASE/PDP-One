# PDP One Windows Connectivity Self-Healing Hotfix Report

## Purpose

This change repairs the Windows startup path after a real incident in which all local PDP One containers and PostgreSQL were healthy, Tailscale reported `Funnel on`, but the public address and ChatGPT MCP connection were not reachable.

## Isolation from concurrent development

- Repository: `PDP-WEBBASE/PDP-One`
- Base branch: `main`
- Base commit: `44a67c405a0ba7352bfcab8ec8ae6b87aa1b4351`
- Hotfix branch: `hotfix/windows-connectivity-self-healing-20260722`
- Concurrent procurement work remains isolated in PR #6 on `feature/procurement-opportunities-phase-1`.
- This hotfix does not modify PR #6, its 154 commits, its database models or its procurement UI.

## Confirmed incident state

- Docker Engine: running
- PostgreSQL: healthy
- Backend, web, MCP, Nginx, Redis, worker and beat: running
- Tailscale container: running and signed in
- Tailscale CLI: reported `Funnel on`
- Local health endpoint: reachable
- Public `.ts.net` endpoint: not reachable from the user browser
- ChatGPT MCP tools: network connection failed
- Active company-network resolver returned only IPv6 addresses while the current path had no usable IPv6 route
- Public resolver returned IPv4 and IPv6 addresses

## Root cause in the previous startup logic

The previous Windows startup logic considered the Tailscale status text sufficient proof of success. If the CLI displayed `Funnel on`, the launcher accepted the public URL even when the actual HTTPS health request failed. The deployment agent also only attempted startup when Nginx was not running; therefore a healthy local Nginx with a broken public route did not trigger repair.

## Implemented changes

### 1. Stable automatic startup

Two Scheduled Tasks are registered:

- `PDP One Stable Startup`
  - runs at Windows logon
  - repeats every ten minutes as a watchdog
  - waits for Rancher Desktop and Docker
  - starts the existing containers without build, pull, migration or token rotation
  - repairs and verifies Tailscale Funnel
- `PDP One Open Local Web`
  - waits for local health after logon
  - opens `http://localhost:8080`
  - avoids dependency on public DNS for use on the same laptop

### 2. Real public-health verification

The new health logic checks, in order:

1. normal Windows HTTPS resolution
2. curl over IPv4
3. public IPv4 resolution through `1.1.1.1` without changing Windows DNS
4. curl with a per-command `--resolve` mapping

A Funnel is accepted only when `/healthz` actually returns the expected PDP One health response.

### 3. Self-repair

When the public route is not usable:

- the Tailscale container is ensured to be running
- Funnel is reapplied
- the public endpoint is tested
- Tailscale is restarted and retried a bounded number of times
- the MCP path token, Tailscale identity and Docker volumes are preserved

### 4. Safe diagnostics

A diagnostic is generated on every startup/update failure and can also be generated manually.

Stable safe-to-share files:

- `C:\PDP-One\PDP-ONE-LAST-DIAGNOSTICS.txt`
- `C:\PDP-One\PDP-ONE-LAST-DIAGNOSTICS.json`
- copies on the Windows Desktop

The diagnostic includes:

- local health
- Docker Compose status
- Scheduled Task state and result
- Tailscale backend state and Funnel status
- Tailscale netcheck
- active resolver result
- public `1.1.1.1` resolver result
- deployment-agent audit tail
- redacted service logs

It removes MCP path tokens, API tokens, passwords, authorization values and secret-bearing URLs.

### 5. Emergency manual tools

- `PDP-ONE-EMERGENCY-START.bat`
  - starts Rancher/Desktop services
  - repairs connectivity
  - opens the local application
  - creates and opens diagnostics if repair fails
- `PDP-ONE-CREATE-DIAGNOSTICS.bat`
  - creates the safe diagnostic without changing data or connectivity identity

### 6. Safer routine launcher

After the one-time connector configuration exists, `CONNECT-CHATGPT.bat` now uses stable startup and repair instead of repeating first-time connector setup. It does not rotate tokens or change Windows DNS.

## First manual update incident and corrective repair

The first emergency update from commit `19570a0f935f1625a02401f56bcc3c94f550ce4d` copied and started the new services, and the public MCP route became reachable. The updater then reported failure because three independent failure-path defects were exposed on real Windows PowerShell 5.1:

1. `manage.py shell` emitted an informational line before `9,2`. Applying `-notmatch` directly to the output array returned the non-matching informational line and caused a false persisted-data failure.
2. `-RestoreDatabase:$migrationAttempted` was forwarded to a child `powershell.exe`; Windows PowerShell 5.1 treated the Boolean expression as text and could not bind it to a switch.
3. the manual deployment ID was empty, so forwarding `-DeploymentId $DeploymentId` produced a parameter with no argument and prevented Diagnostic generation.

Corrective changes:

- the Django output is converted to one text block and an exact `digits,digits` line is parsed;
- the rollback switch is appended as a standalone argument only when database restoration is required;
- manual diagnostics always receive non-empty safe identifiers;
- native Windows PowerShell 5.1 regression tests cover all three cases.

Confirmed after the failed updater window:

- ChatGPT MCP access returned;
- database status: connected;
- contracts: 9;
- receivables: 2;
- deployment agent: configured and queue available;
- no data-loss evidence was observed.

The update was not marked successful because the updater's final state and Scheduled Task registration were not completed. A corrected guarded deployment is still required.

## Data and security impact

Not changed:

- PostgreSQL records
- database schema or migrations
- `postgres_data`
- `private_files`
- `redis_data`
- `tailscale_state`
- `.env` secrets
- MCP path token
- Tailscale node identity
- business modules and UI

## Integration instruction for the concurrent chat

After this hotfix is merged or deployed, the concurrent procurement branch must incorporate the exact hotfix commit before its next deployment. It should not reimplement the startup logic independently. A merge or cherry-pick conflict should be resolved in favor of the hotfix versions of Windows operational scripts, while preserving procurement application changes.

## Deployment gates

The hotfix remains subject to the normal PDP One controls:

1. exact commit
2. CI and Preview
3. explicit approval for that Preview
4. fresh final backup
5. isolated restore verification
6. guarded deployment
7. health check
8. system status
9. deployment report

## Final identifiers

The final commit, Preview ID, backup ID, deployment ID and health results are appended after the guarded deployment is completed.
