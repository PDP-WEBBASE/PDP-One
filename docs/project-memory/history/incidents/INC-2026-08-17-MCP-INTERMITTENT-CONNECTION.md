# INC-2026-08-17 — Intermittent ChatGPT ↔ PDP One MCP connection

- Date: 2026-08-17
- Session: `PDP-SESSION-20260817-MCP-STABILITY`
- Issue: #61
- PR: #66
- Status: **Mitigation implementation in progress — two runtime acceptances failed**

## Symptom reproduced

During read-only diagnosis, PDP One MCP connectivity alternated between success and failure:

1. a governed MCP read succeeded;
2. an immediately following read failed with `mcp_network_error / Connection failed`;
3. a subsequent read succeeded again.

At reproduced failures, PostgreSQL/web/API and the signed deployment queue were healthy in surrounding checks. The incident is therefore an intermittent ChatGPT-facing MCP/public-route failure rather than a persistent database/backend outage.

## Original architecture gaps

- MCP watchdog treated container state/restart count as sufficient health.
- Stable Startup checked public web/API but not token-bound MCP.
- public-route repair could amplify transient external failures into nginx/Tailscale recreation.
- Nginx Streamable HTTP timeout was 300 seconds.
- MCP SDK dependency was not exact-pinned.

Historical PR45/PR46 contain useful incident lineage but are obsolete baselines and are not directly merged.

## First mitigation and runtime acceptance — FAILED

PR66 first added end-to-end MCP `/healthz`, Docker health, token-bound local/public health, 3600-second Streamable HTTP proxy timeouts with buffering/cache disabled, Startup/public checks, route-first self-heal, exact `mcp==1.28.1`, and regression tests.

Exact first deployment:

- commit: `cf99960c7b1155c9c9f0a04fff70f40b40ed7460`
- deployment: `mcp-stability-cf99960c-20260817`
- deployment request: `b1f0d773-0c1c-4d9d-b177-dae91ed59ad8`
- independent health request: `73037eb8-553f-4aac-b190-75b111c64df4`
- deployment result: healthy
- independent health: healthy
- business baseline: PostgreSQL connected, contracts 10, receivables 3

After several successful real MCP calls, a connected `get_system_status` call again failed with `mcp_network_error / Connection failed`, followed by a successful call. PR66 was correctly left unmerged.

## Second mitigation — stateful JSON POST responses

The pinned FastMCP v1.28.1 implementation creates its Streamable HTTP session manager lazily and supports `json_response`/`stateless_http` settings. PR66 therefore configured:

- `mcp.settings.json_response = True` before `mcp.run()` so POST tool responses are short-lived JSON instead of request-scoped SSE response streams;
- `mcp.settings.stateless_http = False` so the guarded stateful session model remains enabled.

Exact second deployment:

- commit: `f364f0564379a3cd3c16c07e6d0f3a925f881c0b`
- deployment: `mcp-stability-json-f364f056-20260817`
- deployment request: `2dcba6e7-3371-48ec-b1cf-12ef1e2d8f23`
- deployment result: healthy
- independent health request: `2717cbf7-3d9a-4e8d-9597-3d860b011148`
- independent health result: healthy

During the independent health window, the Connected MCP route became unavailable for several minutes and then recovered while the layered health request itself completed successfully. `Test-PDPOne.ps1` does not recreate services/routes, so the drop was not caused by that health command. This second acceptance also failed and PR66 remained unmerged.

## Third mitigation — prevent self-heal from amplifying public-only transients

Source audit identified a high-risk feedback loop in the scheduled self-heal architecture:

- `PDP One MCP Self Heal` runs every five minutes;
- when Docker + local token-bound MCP are healthy, the watchdog still probes the public MCP route;
- two failed public observations could send a healthy local installation into `Repair-PDPOneConnectivity.ps1`;
- that repair path could recreate nginx/Tailscale, turning a short external probe miss into a multi-minute ChatGPT disconnect.

PR66 now changes the policy:

1. The five-minute MCP watchdog treats a confirmed **public-only** MCP failure as observational degradation. If Docker health and local token-bound MCP are healthy, it writes `healthy_local_public_degraded_observed` and exits without route/container recreation.
2. Public connectivity repair now requires three observations before disruptive action.
3. If public web + session API are healthy and only the public MCP probe is degraded, the existing Funnel route is preserved and the result is returned as `public_mcp_health=degraded`.
4. nginx/Tailscale recreation remains available only for repeatedly confirmed full public web/API route failure, or for local route/service failures where repair is actually warranted.
5. Stable Startup accepts the non-disruptive MCP-only degraded observation as a warning while keeping local MCP, web/API, data and token continuity healthy.
6. No token rotation, local image build, Docker volume operation, DB mutation, or Tailscale identity reset is introduced.

## Concurrency coordination

A second active Session #68 / PR67 began while PR66 was in acceptance. PR66 and PR67 have no changed-file overlap but share the same old base, so exact deployments could overwrite each other's runtime changes. Session #68 was explicitly instructed to hold PR67 deployment until PR66 completes/merges; PR67 must then refresh onto the new main and rerun its gates before deployment.

## Acceptance still required

Before closing this incident:

- third-mitigation exact-head CI + Windows PowerShell 5.1 success;
- immutable Backend/MCP/Web images success;
- PRE-DEPLOY concurrency sync;
- third exact-commit deployment;
- independent layered health;
- extended repeated **real Connected MCP calls across multiple watchdog periods** with zero `mcp_network_error`;
- contracts remain 10 and receivables remain 3;
- PRE-MERGE sync;
- merge only the accepted exact PR head;
- final Project Memory/session synchronization.

## Safety

No token rotation, database mutation, Docker volume change, Tailscale identity reset, Rancher reset, WSL destructive action, or local application image build is authorized by this incident.
