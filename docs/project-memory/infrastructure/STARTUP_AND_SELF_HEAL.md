# PDP One — Windows Startup and Self-Heal History

## Earlier historical restart model

The `PDPOne-14050426-01-historical-restart-guide.txt` source described an earlier manual reboot procedure:

1. open Rancher Desktop;
2. wait for `CE: moby`;
3. go to `C:\PDP-One`;
4. run `CONNECT-CHATGPT.bat` and keep its console open;
5. the script started the app/database, Tailscale connectivity and ChatGPT connection.

That guide also stated the old process generated a new MCP token/URL each run and could require manually updating ChatGPT.

**Status: Superseded historical procedure.** It must not be used as current startup policy merely because it exists in the archive. Current policy explicitly forbids routine MCP token rotation.

## July 22 Windows hotfix lineage

Hotfix source:

- historical PR #7
- branch `hotfix/windows-connectivity-self-healing-20260722`
- corrected commit cited by handoff: `a508b75735a2a9a560b538f914a88700493950ff`

The hotfix was created after a state where:

- Rancher/Docker were running;
- Backend, Frontend, Nginx, MCP, Redis, Worker and Beat were running;
- Tailscale was logged in;
- command output showed `Funnel on`;
- yet public/MCP access could still be unavailable.

### Root causes / design lessons

- Seeing the literal text `Funnel on` was not sufficient proof of public availability.
- Deployment/startup logic that only reacted to Nginx being down could miss Public/MCP failures while local services were healthy.
- Health must test real expected endpoint behavior, not only process/container existence.

### Stable Startup design

Historical hotfix introduced a `PDP One Stable Startup` Scheduled Task lineage with:

- start Rancher Desktop when required;
- wait for Moby/Docker readiness;
- start/verify PDP One services;
- limited Tailscale Funnel repair;
- real public HTTPS health checks;
- limited self-healing rather than destructive reset.

### Public health logic

The hotfix required real `/healthz` response rather than trusting the text `Funnel on`. It did not intentionally change Windows DNS.

### Limited self-healing

Historical actions included reapplying Funnel and limited Tailscale restart where appropriate. It did **not** justify token rotation, identity reset or destructive data operations.

### Secure diagnostics

Diagnostic bundles were designed to include local health, Compose state, Scheduled Tasks, Tailscale/Funnel/netcheck/DNS/Audit/log evidence while redacting token/password/authorization/secret/private MCP URL data.

### Historical PowerShell bugs fixed

The handoff records three defects in an initial manual hotfix attempt:

1. false persisted-sample-data evaluation caused by multi-line Django output / PowerShell array matching;
2. rollback parameter binding issue;
3. diagnostic handling with an empty DeploymentId.

Native Windows PowerShell 5.1 regression tests were added.

### What the hotfix intentionally did not change

Historical handoff explicitly preserved:

- MCP path token
- Tailscale identity
- Windows DNS
- Docker/business data volumes
- procurement feature work in the parallel procurement branch

## Current governance

Treat the above as architecture/incident history. Before any current startup repair:

- read current GitHub Windows scripts;
- read live runtime/Deployment Agent state;
- inspect current accepted startup/reboot evidence;
- never rotate MCP token or reset Tailscale/Rancher just because an old guide once did something different.
