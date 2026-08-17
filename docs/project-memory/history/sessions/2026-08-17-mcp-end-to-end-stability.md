# PDP Session Log — MCP end-to-end stability hardening

- Session ID: `PDP-SESSION-20260817-MCP-STABILITY`
- Active-work Issue: #61
- Implementation PR: #66
- Date: 2026-08-17
- Status: **COMPLETED**

## Goal

Eliminate the repeatedly reproduced intermittent ChatGPT ↔ PDP One MCP connection failure without rotating the MCP token, changing PostgreSQL/business data, touching Docker volumes, resetting Tailscale identity, or building application images locally.

## Starting state

- Starting GitHub main observed by Session #61: `be268574fac4a8786664426535f57ce3003f9a35`.
- Historical deployed application at session start: `d2d70c67f5e1e3290a6a165b953118e4e7f90c9f`.
- Web/API/PostgreSQL were reachable while real Connected MCP reads intermittently failed with `mcp_network_error / Connection failed`.
- Historical PR45/PR46 were not merged; required stability behavior was reimplemented from current main.

## Implemented policy

PR66 established end-to-end MCP health and non-disruptive self-heal behavior:

- explicit MCP service `/healthz`;
- Docker MCP healthcheck and nginx dependency on healthy MCP;
- token-bound local/public MCP health route without opening a protocol session;
- Streamable HTTP proxy buffering/cache disabled with 3600-second read/send timeouts;
- Stable Startup validates local/public MCP health as well as web/API;
- watchdog validates Docker health, restart stability and local token-bound MCP route;
- healthy local MCP + public-only degradation is observational and does not trigger nginx/Tailscale recreation;
- disruptive public-route repair requires stronger repeated full web/API failure evidence;
- stateful Streamable HTTP retained, with JSON POST responses enabled and `stateless_http=false`;
- MCP SDK pinned to stable `mcp==1.28.1`;
- regression/Windows PowerShell contract coverage added.

## Deployment / acceptance lineage

### First mitigation

- exact commit: `cf99960c7b1155c9c9f0a04fff70f40b40ed7460`
- deployment: `mcp-stability-cf99960c-20260817`
- deploy request: `b1f0d773-0c1c-4d9d-b177-dae91ed59ad8`
- result: succeeded / healthy
- independent health request: `73037eb8-553f-4aac-b190-75b111c64df4` → healthy
- runtime acceptance: **failed** after the intermittent Connected MCP error reproduced again.

### Second mitigation

- exact commit: `f364f0564379a3cd3c16c07e6d0f3a925f881c0b`
- deployment: `mcp-stability-json-f364f056-20260817`
- deploy request: `2dcba6e7-3371-48ec-b1cf-12ef1e2d8f23`
- result: succeeded / healthy
- independent health request: `2717cbf7-3d9a-4e8d-9597-3d860b011148` → healthy
- runtime acceptance: **failed** after a multi-minute Connected MCP outage during the acceptance window.

### Third mitigation / accepted runtime

- exact PR66 head and exact deployed application commit: `ee4095e2d9afca030e4bda4eff9608d6a1e8138b`
- deployment: `mcp-stability-hysteresis-ee4095e2-20260817`
- deploy request: `a05290f2-a168-483d-a26c-7781eff977b7`
- deploy result: succeeded / healthy
- independent health request: `457e3555-3fab-44f3-8c8f-f29e4362f084` → succeeded / healthy
- exact-head gates: Memory Governance success; PDP One CI run `32048388629` success; immutable images run `32048388666` success.
- extended real Connected MCP acceptance crossed more than two five-minute watchdog periods (>11 minutes).
- recorded checkpoints included 8/8 successful reads followed by 6/6 additional alternating `get_deployment_status` / `get_system_status` reads.
- zero `mcp_network_error / Connection failed` was reproduced outside the deployment restart window during the final acceptance.
- PostgreSQL remained connected; contracts remained 10; receivables remained 3; deployment queue remained pending=0.

## Merge

- PR66 merged: 2026-08-17.
- accepted PR head: `ee4095e2d9afca030e4bda4eff9608d6a1e8138b`.
- merge commit: `7cc0c025cec69dbe161acb56cedf832f63867c38`.
- exact deployed application identity remains the accepted PR head, not the merge commit.

## Concurrency

Session #68 / PR67 started during PR66 acceptance. The workstreams had no final changed-file overlap, but exact application deployments were sequenced so PR67 could not overwrite PR66 before acceptance. PR67 was refreshed onto the PR66 merge before its own deployment flow. Session #74 is frontend-only and does not overlap this MCP closure record.

## Safety preserved

- no MCP token rotation;
- no Tailscale identity reset;
- no PostgreSQL/business-data mutation;
- no Docker volume prune/change;
- no Rancher/WSL destructive operation;
- no local application image build;
- no duplicate deploy write after any accepted Request ID.

## Final result

**PASS.** The third mitigation met the recorded runtime acceptance requirement, PR66 was merged, and the permanent incident/session evidence is synchronized. Session Issue #61 may be closed as completed.
