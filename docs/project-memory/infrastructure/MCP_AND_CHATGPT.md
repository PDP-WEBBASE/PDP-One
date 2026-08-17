# PDP One — MCP and ChatGPT Integration

## Purpose

The PDP One connector/MCP surface gives ChatGPT controlled access to domain reads, draft writes and deployment-agent operations without exposing arbitrary shell.

## Secret rule

Never store or display:

- private MCP token
- private tokenized MCP URL
- authorization material
- session secrets

The project-memory registry records the logical connector/access method only.

## Token policy evolution

An early historical restart guide described creating a new MCP token/URL during each manual startup and updating the ChatGPT connection.

That model is **superseded**.

Current hard rule:

> Do not rotate a working MCP token unless the user explicitly instructs token rotation.

Startup/recovery should repair services/connectivity without gratuitous credential changes.

## Runtime disconnect behavior

The connector may temporarily disconnect while MCP/application services restart during deployment. If a deployment Request ID has already been accepted, do not send a duplicate deploy; wait for reconnection and read the same request report.

Intermittent disconnects outside a deployment are not considered healthy merely because the MCP Docker container is `running`.

## End-to-end MCP health policy — 2026-08-17

Session #61 / PR66 established that MCP health must be proven across the actual connection path:

1. MCP service `/healthz` inside the container;
2. Docker MCP health status;
3. local token-bound Nginx → MCP health;
4. public Tailscale Funnel → Nginx → MCP health;
5. real ChatGPT tool calls for post-deployment acceptance.

A healthy web shell, session API, or running container is not sufficient proof of MCP health.

The external health probe is deliberately exposed only at the existing private token path; the token value itself is never written to GitHub or reports.

### Self-heal behavior

- healthy MCP container + failed local route → repair the route first;
- unhealthy/missing MCP container → validate image import and recreate only MCP using the configured immutable image;
- never build MCP locally during self-heal;
- use `--no-build --pull never`;
- a confirmed **public-only MCP degradation** while Docker/local MCP and public web/API remain healthy is observational and must not by itself recreate nginx/Tailscale;
- disruptive public-route repair requires stronger repeated full web/API failure evidence;
- defer self-heal during a coordinated exact-commit deployment.

### Streamable HTTP proxy

The token-bound MCP route is configured for long-lived Streamable HTTP:

- proxy/request buffering off;
- proxy cache off;
- read/send timeout 3600 seconds;
- a separate short-lived token-bound `/healthz` route is used for monitoring without opening a protocol session.

### MCP SDK / transport behavior

For PR66 the stable v1 SDK is pinned exactly to `mcp==1.28.1` for reproducibility. Migration to an MCP v2 prerelease is explicitly outside this incident repair.

The accepted runtime keeps the guarded stateful Streamable HTTP model (`stateless_http=false`) while enabling JSON POST responses so ordinary tool responses are short-lived JSON rather than request-scoped SSE streams.

An upstream v1.28.1 client-disconnect issue remains an external risk to revisit when an appropriate stable patched release is available; it is not a reason to adopt a beta transport in an emergency stability fix.

## Accepted Session #61 runtime identity

The final accepted PR66 application head was:

- exact deployed commit: `ee4095e2d9afca030e4bda4eff9608d6a1e8138b`
- deployment: `mcp-stability-hysteresis-ee4095e2-20260817`
- deploy request: `a05290f2-a168-483d-a26c-7781eff977b7` → succeeded / healthy
- independent health request: `457e3555-3fab-44f3-8c8f-f29e4362f084` → succeeded / healthy
- PR66 merge commit: `7cc0c025cec69dbe161acb56cedf832f63867c38`

Final Connected MCP acceptance crossed more than two five-minute watchdog periods (>11 minutes), with recorded 8/8 successful reads followed by 6/6 additional alternating Connected MCP reads and zero reproduced `mcp_network_error / Connection failed` outside the deployment restart window. PostgreSQL remained connected and the business-data baseline stayed at 10 contracts / 3 receivables.

The deployed exact commit and merge commit are intentionally tracked as different identities.

See:

- `docs/project-memory/decisions/ADR-037-MCP-END-TO-END-HEALTH.md`
- `docs/project-memory/history/incidents/INC-2026-08-17-MCP-INTERMITTENT-CONNECTION.md`
- `docs/project-memory/history/sessions/2026-08-17-mcp-end-to-end-stability.md`

## Capability boundaries

The connector exposes governed domain/deployment actions. Current Deployment Agent state explicitly reports arbitrary shell disabled.

Use read tools before writes where required. Contract/financial artifacts created by AI remain Draft according to project policy.

## Project-memory protocol

A new chat must not mutate PDP One merely because the connector is available.

Mutation additionally requires:

1. user activation with `PDPONE START` for the Conversation;
2. GitHub Project Memory Context Sync;
3. concurrent-work check;
4. Session Issue and scope declaration for material work;
5. applicable domain safety checks.

## Historical transfer limitation

Transfer packages can preserve connector configuration/evidence but cannot carry a live authenticated ChatGPT/MCP session to another chat/machine. New sessions must use the currently connected tool and verify runtime state live.
