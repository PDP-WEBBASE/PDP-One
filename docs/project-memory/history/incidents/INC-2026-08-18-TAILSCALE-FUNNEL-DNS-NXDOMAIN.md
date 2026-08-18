# INC-2026-08-18 — Tailscale Funnel hostname returned NXDOMAIN after Windows startup

- Date: 2026-08-18
- Session: `PDP-SESSION-20260818-TAILSCALE-FUNNEL-DNS-RECOVERY`
- Issue: #85
- Status: **IMPLEMENTATION IN PROGRESS**

## Symptom and evidence

After Windows logon, PDP One local services were healthy but ChatGPT could not reach MCP.

Sanitized diagnostics established:

- local PDP One health returned HTTP 200;
- Docker, PostgreSQL, backend, web and token-bound local MCP were healthy;
- Tailscale `BackendState` was `Running`;
- `tailscale funnel status` advertised the expected public hostname and proxy;
- both the active Windows resolver and public resolver `1.1.1.1` returned `NXDOMAIN`;
- public health and real ChatGPT MCP calls failed;
- `PDP One Stable Startup` did run, so this was not a missing Scheduled Task trigger.

## Root cause

The startup path treated the persisted text `Funnel on` as sufficient proof of public publication. A persisted Funnel configuration could survive reboot while the hostname was absent from public DNS. Recreating nginx and the Tailscale container retained the stale Funnel configuration and did not force bounded republishing.

The Scheduled Task also used 20 one-minute failure retries, amplifying deterministic DNS failure into a restart storm while the local application was already healthy.

## Repair design

- Verify public DNS publication independently of Funnel status.
- Wait for a bounded publication window after startup.
- If DNS is still unpublished, run the documented `tailscale funnel reset` command and register only the Funnel target again.
- Perform at most one Funnel configuration reset per connectivity-repair execution.
- Preserve the Tailscale node identity, MCP token, nginx, Docker volumes, PostgreSQL and application data.
- Keep the existing stronger evidence requirement for disruptive nginx/Tailscale recreation.
- Limit Stable Startup failure retries to one delayed retry; the ten-minute watchdog remains the longer-term retry mechanism.

## Explicit exclusions

- no `tailscale logout`, identity reset or auth-key rotation;
- no MCP token rotation;
- no Rancher reset, WSL unregister or Docker volume operation;
- no database or business-data mutation;
- no local application-image build.

## Acceptance required

1. Exact-head CI and Windows PowerShell contract tests pass.
2. PRE-DEPLOY Delta Sync finds a clear/sequenced deployment lane.
3. Exact immutable deployment applies the updated Windows scripts and Scheduled Task registration.
4. Public DNS resolves, public web/API/MCP health passes, and a real ChatGPT tool call succeeds.
5. Project Memory is finalized and the Session Issue is closed only after runtime evidence.
