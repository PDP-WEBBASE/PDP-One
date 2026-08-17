# INC-2026-08-17 — Intermittent ChatGPT ↔ PDP One MCP connection

- Date: 2026-08-17
- Session: `PDP-SESSION-20260817-MCP-STABILITY`
- Issue: #61
- PR: #66
- Status: **Mitigation implementation in progress**

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

The existing health model could report the system as healthy while ChatGPT could not reach MCP:

- MCP watchdog checked container state/restart count, not the MCP HTTP endpoint;
- Stable Startup checked public web/API but not MCP;
- public-route repair checked public web/API but not the token-bound MCP route;
- Nginx Streamable HTTP timeout was 300 seconds;
- healthy-container route failure and unhealthy-container failure were not differentiated strongly enough.

## Historical relation

Historical PR45 recorded an earlier, different MCP incident: a restart loop caused by a missing Python module in the MCP image. Historical PR46 addressed deployment/startup/disk coordination races. Their useful safety lessons are preserved, but neither stale branch is directly merged into the 2026-08-17 baseline.

## Implemented mitigation on PR66

- explicit MCP `/healthz` service route;
- Docker MCP healthcheck;
- nginx waits for MCP `service_healthy`;
- token-bound local/public MCP health path;
- 3600-second Streamable HTTP read/send timeout and buffering/cache disabled;
- Stable Startup validates local/public MCP health;
- public route failure is rechecked before disruptive recreate;
- watchdog uses Docker health + route health and prefers route repair before recreating a healthy MCP container;
- stable MCP SDK v1 exact pin for reproducibility;
- contract tests.

## Acceptance still required

Before closing this incident:

- final-head CI success;
- immutable image build success;
- exact-commit deployment;
- independent health;
- multiple alternating MCP calls after deployment without reproduced network failure;
- unchanged business-data safety checks;
- final memory/session synchronization.

## Safety

No token rotation, database mutation, Docker volume change, Tailscale identity reset, Rancher reset, WSL destructive action, or local application image build is authorized by this incident.
