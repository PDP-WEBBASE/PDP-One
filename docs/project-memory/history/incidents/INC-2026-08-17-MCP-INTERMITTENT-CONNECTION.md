# INC-2026-08-17 — Intermittent ChatGPT ↔ PDP One MCP connection

- Date: 2026-08-17
- Session: `PDP-SESSION-20260817-MCP-STABILITY`
- Issue: #61
- PR: #66
- Status: **RESOLVED / ACCEPTED / MERGED**

## Symptom reproduced

During read-only diagnosis, PDP One MCP connectivity alternated between success and failure:

1. a governed MCP read succeeded;
2. an immediately following read failed with `mcp_network_error / Connection failed`;
3. a subsequent read succeeded again.

At reproduced failures, PostgreSQL/web/API and the signed deployment queue were healthy in surrounding checks. The incident was therefore an intermittent ChatGPT-facing MCP/public-route failure rather than a persistent database/backend outage.

## Original architecture gaps

- MCP watchdog treated container state/restart count as sufficient health.
- Stable Startup checked public web/API but not token-bound MCP.
- public-route repair could amplify transient external failures into nginx/Tailscale recreation.
- Nginx Streamable HTTP timeout was 300 seconds.
- MCP SDK dependency was not exact-pinned.

Historical PR45/PR46 contain useful incident lineage but are obsolete baselines and were not directly merged into this fix.

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

## Second mitigation — stateful JSON POST responses — FAILED

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

## Third mitigation — prevent self-heal from amplifying public-only transients — ACCEPTED

Source audit identified a high-risk feedback loop in the scheduled self-heal architecture:

- `PDP One MCP Self Heal` runs every five minutes;
- when Docker + local token-bound MCP are healthy, the watchdog still probes the public MCP route;
- repeated public probe misses could send a healthy local installation into disruptive public-route repair;
- route recreation could turn a short external probe miss into a multi-minute ChatGPT disconnect.

The accepted PR66 policy is:

1. The five-minute MCP watchdog treats a confirmed **public-only** MCP failure as observational degradation. If Docker health and local token-bound MCP are healthy, it records the degraded observation and exits without route/container recreation.
2. Public connectivity repair requires stronger repeated evidence before disruptive action.
3. If public web + session API are healthy and only the public MCP probe is degraded, the existing Funnel route is preserved and the condition is reported as degraded instead of repaired disruptively.
4. nginx/Tailscale recreation remains available only for repeatedly confirmed full public web/API route failure, or for local route/service failures where repair is warranted.
5. Stable Startup accepts non-disruptive MCP-only degradation as a warning while keeping local MCP, web/API, data and token continuity healthy.
6. No token rotation, local image build, Docker volume operation, DB mutation, or Tailscale identity reset is introduced.

Accepted third deployment:

- exact PR66 head / exact deployed commit: `ee4095e2d9afca030e4bda4eff9608d6a1e8138b`
- deployment: `mcp-stability-hysteresis-ee4095e2-20260817`
- deployment request: `a05290f2-a168-483d-a26c-7781eff977b7` → succeeded / healthy
- independent health request: `457e3555-3fab-44f3-8c8f-f29e4362f084` → succeeded / healthy
- exact-head Memory Governance: success
- exact-head CI run: `32048388629` → success
- exact-head immutable images run: `32048388666` → success

## Final runtime acceptance

The final Connected MCP acceptance crossed more than two five-minute watchdog periods (>11 minutes). Recorded checkpoints included:

- 8/8 real Connected MCP reads PASS;
- 6/6 additional alternating `get_deployment_status` / `get_system_status` reads PASS;
- zero `mcp_network_error / Connection failed` outside the deployment restart window;
- PostgreSQL connected;
- contracts=10;
- receivables=3;
- deployment queue pending=0.

This satisfied the Session #61 runtime acceptance requirement.

## Merge / resolution

PRE-MERGE coordination was completed after acceptance. PR67 had already removed final file-level overlap with PR66 and was sequenced so it could not overwrite the accepted PR66 runtime before merge.

PR66 was merged with:

- accepted PR head: `ee4095e2d9afca030e4bda4eff9608d6a1e8138b`
- merge commit: `7cc0c025cec69dbe161acb56cedf832f63867c38`

The exact deployed application identity remains the accepted PR head; the merge commit is a distinct GitHub object.

## Safety outcome

Throughout the incident there was:

- no MCP token rotation;
- no database/business-data mutation;
- no Docker volume change/prune;
- no Tailscale identity reset;
- no Rancher reset or WSL destructive action;
- no local application image build;
- no duplicate deployment after an accepted Request ID.

## Permanent evidence

- Session Log: `docs/project-memory/history/sessions/2026-08-17-mcp-end-to-end-stability.md`
- ADR: `docs/project-memory/decisions/ADR-037-MCP-END-TO-END-HEALTH.md`
- MCP summary: `docs/project-memory/infrastructure/MCP_AND_CHATGPT.md`
- Session Issue: #61
- Implementation PR: #66

**Resolution: PASS.**
