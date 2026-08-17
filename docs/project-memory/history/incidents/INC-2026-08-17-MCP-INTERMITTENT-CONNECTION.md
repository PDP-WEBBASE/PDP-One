# INC-2026-08-17 — Intermittent ChatGPT ↔ PDP One MCP connection

- Date: 2026-08-17
- Session: `PDP-SESSION-20260817-MCP-STABILITY`
- Issue: #61
- Runtime PR: #66
- Status: **Resolved / live accepted**
- Resolved at: 2026-08-17 ~20:55 Asia/Tehran

## Symptom

Connected ChatGPT MCP calls intermittently alternated between success and `mcp_network_error / Connection failed` while PostgreSQL, web/API and the Deployment Agent remained healthy in surrounding checks. The failure was therefore a ChatGPT-facing MCP/public-route stability incident rather than a persistent database/backend outage.

## Root causes and architecture gaps

The incident exposed multiple layers that had to be corrected together:

1. the MCP watchdog originally treated a running/stable container as sufficient health;
2. Stable Startup/public repair did not prove the token-bound MCP route end to end;
3. the Nginx Streamable HTTP route used a 300-second read timeout;
4. the MCP SDK dependency was not exact-pinned;
5. request-scoped SSE responses increased dependence on long-lived response streams;
6. most importantly, the five-minute self-heal loop could amplify a short **public-only MCP probe miss** into a disruptive nginx/Tailscale recreation even when Docker, local MCP, public web and public API were healthy.

The final accepted mitigation therefore treats public-only MCP degradation as observational and non-disruptive rather than a reason to recreate the stable Funnel route.

## Mitigation lineage

### First mitigation — health/route observability

PR66 added explicit MCP `/healthz`, Docker MCP health, token-bound local/public health, 3600-second proxy timeouts, disabled MCP proxy buffering/cache, Stable Startup checks, route-first self-heal, exact `mcp==1.28.1`, and regression tests.

First exact deployment:

- commit: `cf99960c7b1155c9c9f0a04fff70f40b40ed7460`
- deployment: `mcp-stability-cf99960c-20260817`
- deploy request: `b1f0d773-0c1c-4d9d-b177-dae91ed59ad8`
- independent health request: `73037eb8-553f-4aac-b190-75b111c64df4`

Deployment/health passed, but a later real Connected MCP call reproduced the intermittent network failure. Acceptance failed and PR66 remained unmerged.

### Second mitigation — stateful JSON responses

FastMCP v1.28.1 was configured before `mcp.run()` with:

- `mcp.settings.json_response = True`;
- `mcp.settings.stateless_http = False`.

This preserved stateful Streamable HTTP while making POST tool responses short-lived JSON instead of request-scoped SSE response streams.

Second exact deployment:

- commit: `f364f0564379a3cd3c16c07e6d0f3a925f881c0b`
- deployment: `mcp-stability-json-f364f056-20260817`
- deploy request: `2dcba6e7-3371-48ec-b1cf-12ef1e2d8f23`
- independent health request: `2717cbf7-3d9a-4e8d-9597-3d860b011148`

Deployment/health passed, but Connected MCP became unavailable for several minutes during acceptance and later recovered. Acceptance failed again and PR66 remained unmerged.

### Third mitigation — non-disruptive self-heal hysteresis

The accepted final policy is:

- if Docker health and the local token-bound MCP route are healthy, a confirmed **public-only** MCP probe failure is recorded as `degraded_observed` and the watchdog exits without recreating nginx, Tailscale or MCP;
- public connectivity repair uses three observations before disruptive action;
- if public web + session API are healthy while only public MCP is degraded, preserve the existing Funnel route and return `public_mcp_health=degraded`;
- nginx/Tailscale recreation is reserved for repeatedly confirmed full public web/API route failure or genuine local route/service failure;
- Stable Startup treats public-MCP-only degradation as a warning while preserving the healthy local MCP/web/API/data path;
- no token rotation, Tailscale identity reset, DB mutation, Docker volume operation or local application build is part of the fix.

## Final exact deployment and acceptance

Accepted exact production commit:

`ee4095e2d9afca030e4bda4eff9608d6a1e8138b`

Deployment evidence:

- deployment ID: `mcp-stability-hysteresis-ee4095e2-20260817`
- deploy request: `a05290f2-a168-483d-a26c-7781eff977b7`
- deploy result: `succeeded / healthy`
- independent health request: `457e3555-3fab-44f3-8c8f-f29e4362f084`
- independent health result: `succeeded / healthy`
- change-management mode: `development_fast`
- automatic rollback: not used / not available in development-fast

Live Connected MCP acceptance:

- acceptance window: **more than 11 minutes**;
- spanned more than two five-minute watchdog periods;
- initial post-health real reads: PASS;
- checkpoint after >5 minutes: **6/6** Connected MCP reads PASS;
- final checkpoint after >10 minutes: **8/8** Connected MCP reads PASS;
- zero `mcp_network_error` / `Connection failed` outside the expected deployment restart window;
- final PostgreSQL state: connected;
- contracts: **10**;
- receivables: **3**;
- Deployment Agent pending requests: **0**.

The final runtime PR was merged only after this acceptance passed.

## Merge identity

- exact deployed PR66 head: `ee4095e2d9afca030e4bda4eff9608d6a1e8138b`
- PR66 merge SHA: `7cc0c025cec69dbe161acb56cedf832f63867c38`

These are intentionally separate identities. Production was accepted on the exact PR head; the merge commit is the canonical GitHub lineage after acceptance.

## Concurrency resolution

Session #68 / PR67 overlapped in deployment timing but not MCP source files. Because exact deployment replaces the full image set, PR67 was placed in SEQUENCE/HOLD while PR66 completed live acceptance. After PR66 merge, PR67 must refresh onto the new `main`, rerun exact-head CI + immutable images, and only then perform a new PRE-DEPLOY sync/deployment. Old-base PR67 heads must not be deployed over the accepted PR66 runtime.

## Permanent safety constraints

- No automatic MCP token rotation during startup/recovery.
- No Tailscale identity reset as a troubleshooting reflex.
- No Rancher Factory Reset / WSL unregister / VHDX deletion.
- No Docker volume prune or business-data mutation.
- No local application image build.
- Real Connected MCP traffic remains a required post-deployment acceptance layer; `/healthz` alone is not sufficient proof of ChatGPT-facing stability.
