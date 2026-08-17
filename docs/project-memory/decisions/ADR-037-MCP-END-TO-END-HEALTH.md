# ADR-037 — MCP end-to-end health and stability policy

- Date: 2026-08-17
- Session: `PDP-SESSION-20260817-MCP-STABILITY`
- Issue: #61
- Implementation PR: #66
- Status: **Approved / implementation in progress**

## Context

PDP One MCP connectivity was reproduced as intermittent from ChatGPT: one governed MCP read could succeed, the immediately following read could fail with `mcp_network_error / Connection failed`, and a later read could succeed again. During the reproduced failure the Deployment Agent had no pending deployment and PostgreSQL/web/API remained reachable.

The prior health architecture had an observability gap:

- `Ensure-PDPOneMcpHealthy.ps1` accepted a container that was `running` with a stable restart count without probing the MCP HTTP surface;
- Stable Startup validated public web `/healthz` and the session API but not the token-bound MCP route;
- public connectivity repair could accept web/API success while MCP remained unreachable;
- the Nginx Streamable HTTP route had a 300-second read timeout;
- the MCP dependency was a floating stable-v1 range rather than an exact reproducible version.

Historical PR45/PR46 contain relevant incident lineage but are based on obsolete baselines. They must not be directly merged into current `main`.

## Decision

PDP One MCP health is **end-to-end**, not container-only.

The accepted health layers are:

1. MCP process/service health inside the container (`/healthz`);
2. Docker health status for the MCP service;
3. local token-bound Nginx → MCP health (`/mcp/<private-token>/healthz`);
4. public Tailscale Funnel → Nginx → MCP health on the same token-bound health route;
5. actual ChatGPT MCP tool calls as post-deployment acceptance evidence.

A healthy web shell or API alone is not proof that MCP is healthy.

## Self-heal policy

- A healthy MCP container with a broken route should trigger **route repair first**, not MCP container recreation.
- An MCP container may be recreated only when its own Docker/service health is not healthy or recovery requires it.
- Public-route repair must confirm a transient failure with a second check before disruptive nginx/Tailscale recreation.
- Self-heal remains disabled/deferred during a coordinated exact-commit deployment.
- Self-heal must never build application images locally and must use `--no-build --pull never`.

## Streamable HTTP proxy policy

For the token-bound MCP endpoint:

- proxy buffering: off;
- request buffering: off;
- proxy cache: off;
- read/send timeout: 3600 seconds;
- health probe uses a separate short-lived token-bound `/healthz` route and does not create an MCP protocol session.

## SDK policy

For this change, remain on stable MCP Python SDK v1 and pin the exact version `mcp==1.28.1` for reproducibility. Do not migrate this production path to an MCP v2 prerelease as part of an incident fix.

A known upstream v1.28.1 client-disconnect issue remains a tracked external risk; revisit when an appropriate stable patched release exists and only through a separately tested change.

## Security

The underlying MCP service health route is intentionally non-secret, but Nginx exposes it externally only behind the existing private path token. The private token itself is never committed, logged, or recorded in Project Memory.

No MCP token rotation is part of this decision.

## Data/runtime safety

This change must not:

- mutate PostgreSQL/business data;
- alter Docker volumes;
- reset Tailscale identity;
- reset Rancher/WSL;
- locally build application images.

## Deployment

Use active `development_fast` policy:

`Branch → CI → immutable exact images → exact-commit deploy → independent health → repeated MCP acceptance → merge`

Exact deployment evidence is recorded in Issue #61 / PR66 and will be synchronized into the final Session Log/Current State after the runtime PR reaches terminal state.
