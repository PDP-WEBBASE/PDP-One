# PDP Session — Tailscale Funnel DNS recovery after Windows startup

- Session ID: `PDP-SESSION-20260818-TAILSCALE-FUNNEL-DNS-RECOVERY`
- Date: 2026-08-18
- Issue: #85
- Branch: `fix/tailscale-funnel-dns-recovery-20260818`
- Starting main: `320c6f57808f732ec3159d10d2c5f1f1a3eb04bc`
- Phase: IMPLEMENTATION / CI PENDING
- Concurrency: SPLIT implementation; SEQUENCE deployment with #79/#80

## User request

Restore reliable automatic ChatGPT/PDP One connectivity after Windows startup.

## Verified diagnosis

The local application, database and local MCP route were healthy. Tailscale reported Running and Funnel on, but the hostname returned NXDOMAIN through both the Windows resolver and 1.1.1.1. Stable Startup was running and repeatedly failing.

## Implementation checkpoint

- Added bounded public-DNS publication checks.
- Added one safe Funnel-only reset/re-registration when the hostname remains unpublished.
- Preserved Tailscale identity, MCP token, local services and data.
- Reduced the Stable Startup failure-restart storm from 20 one-minute retries to one retry after five minutes, while retaining the ten-minute watchdog.
- Added focused contract assertions.
- Recorded incident evidence without secrets.

## Remaining

Exact CI, PRE-DEPLOY Delta Sync, immutable deployment, DNS/public health/real MCP acceptance, final memory sync and merge.
