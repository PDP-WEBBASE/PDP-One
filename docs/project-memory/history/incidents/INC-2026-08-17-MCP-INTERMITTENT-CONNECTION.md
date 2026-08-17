# INC-2026-08-17 — Intermittent ChatGPT ↔ PDP One MCP connection

- Date: 2026-08-17
- Session: `PDP-SESSION-20260817-MCP-STABILITY`
- Issue: #61
- PR: #66
- Status: **Mitigation implementation in progress — first runtime acceptance failed**

## Symptom reproduced

During read-only diagnosis, PDP One MCP connectivity alternated between success and failure:

1. a governed MCP read succeeded;
2. an immediately following read failed with `mcp_network_error / Connection failed`;
3. a subsequent read succeeded again.

At the reproduced failure:

- Deployment Agent pending requests: 0;
- signed deployment queue: available;
- PostgreSQL: reachable;
- PDP One web/API: reachable in surrounding checks.

Therefore the incident is an intermittent MCP/public-route connectivity failure rather than a persistent database/backend outage or a normal deployment restart.

## Root-cause architecture gap

The original health model could report the system as healthy while ChatGPT could not reach MCP:

- MCP watchdog checked container state/restart count, not the MCP HTTP endpoint;
- Stable Startup checked public web/API but not MCP;
- public-route repair checked public web/API but not the token-bound MCP route;
- Nginx Streamable HTTP timeout was 300 seconds;
- healthy-container route failure and unhealthy-container failure were not differentiated strongly enough.

The first mitigation closed those observability/self-heal gaps, but production acceptance proved that service health alone was not sufficient: the ChatGPT-facing Streamable HTTP request path still reproduced one transient connection failure after multiple successful calls.

## Historical relation

Historical PR45 recorded an earlier, different MCP incident: a restart loop caused by a missing Python module in the MCP image. Historical PR46 addressed deployment/startup/disk coordination races. Their useful safety lessons are preserved, but neither stale branch is directly merged into the 2026-08-17 baseline.

## First mitigation and deployment

PR66 first implemented:

- explicit MCP `/healthz` service route;
- Docker MCP healthcheck;
- nginx waits for MCP `service_healthy`;
- token-bound local/public MCP health path;
- 3600-second Streamable HTTP read/send timeout and buffering/cache disabled;
- Stable Startup validates local/public MCP health;
- public route failure is rechecked before disruptive recreate;
- watchdog uses Docker health + route health and prefers route repair before recreating a healthy MCP container;
- stable MCP SDK v1 exact pin `mcp==1.28.1`;
- regression contract tests.

Exact first deployment:

- commit: `cf99960c7b1155c9c9f0a04fff70f40b40ed7460`
- deployment: `mcp-stability-cf99960c-20260817`
- deployment request: `b1f0d773-0c1c-4d9d-b177-dae91ed59ad8`
- independent health request: `73037eb8-553f-4aac-b190-75b111c64df4`
- deployment result: healthy
- independent layered health: healthy
- business baseline after deploy: PostgreSQL connected, contracts 10, receivables 3

## First live acceptance result — FAILED

After the first deployment, several real connected MCP reads succeeded, including system/deployment status reads. A later real `get_system_status` call reproduced `mcp_network_error / Connection failed`. The immediately following governed MCP read succeeded again.

This proves:

- the incident is not resolved;
- the failure remains intermittent rather than a persistent MCP/container/database outage;
- PR66 must not be merged or the incident closed based only on Docker/local/public `/healthz` checks;
- real ChatGPT tool traffic remains a mandatory acceptance gate.

## Second mitigation — stateful JSON responses

The pinned `mcp==1.28.1` FastMCP implementation supports both `json_response` and `stateless_http` settings, and creates its Streamable HTTP session manager lazily. PR66 therefore now configures:

- `mcp.settings.json_response = True` before `mcp.run()` so each POST returns a short-lived JSON response instead of a request-scoped SSE response stream;
- `mcp.settings.stateless_http = False` so the existing stateful session model is retained.

This is intentionally narrower than migrating to MCP v2 or rewriting the service on the low-level server API. Stateless v1 mode is not enabled as part of this incident fix.

## Acceptance still required

Before closing this incident:

- final-head CI success;
- immutable image build success;
- second exact-commit deployment;
- independent health;
- extended repeated real ChatGPT MCP calls over multiple minutes with no reproduced network failure;
- unchanged business-data safety checks;
- PRE-MERGE concurrency/context sync;
- merge exact accepted PR head;
- final Project Memory/session synchronization.

## Safety

No token rotation, database mutation, Docker volume change, Tailscale identity reset, Rancher reset, WSL destructive action, or local application image build is authorized by this incident.
