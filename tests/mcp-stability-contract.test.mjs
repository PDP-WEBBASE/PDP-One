import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const load = (path) => readFile(new URL(path, import.meta.url), "utf8");

test("MCP image exposes an explicit health route and pins stable v1 SDK", async () => {
  const entry = await load("../services/pdp_mcp/server_procurement.py");
  const health = await load("../services/pdp_mcp/health_tools.py");
  const dockerfile = await load("../services/pdp_mcp/Dockerfile");
  const requirements = await load("../services/pdp_mcp/requirements.txt");

  assert.match(entry, /register_health_route\(mcp\)/);
  assert.match(health, /custom_route\("\/healthz", methods=\["GET"\]/);
  assert.match(health, /pdp-one-mcp/);
  assert.match(dockerfile, /health_tools\.py/);
  assert.match(requirements, /^mcp==1\.28\.1$/m);
});

test("MCP keeps stateful sessions while returning short-lived JSON POST responses", async () => {
  const entry = await load("../services/pdp_mcp/server_procurement.py");

  assert.match(entry, /mcp\.settings\.json_response\s*=\s*True/);
  assert.match(entry, /mcp\.settings\.stateless_http\s*=\s*False/);
  assert.match(entry, /mcp\.run\(transport="streamable-http"\)/);
  assert.doesNotMatch(entry, /stateless_http\s*=\s*True/);
});

test("Compose and nginx require MCP health and preserve long-lived streamable HTTP", async () => {
  const compose = await load("../docker-compose.yml");
  const nginx = await load("../infra/nginx/default.conf.template");

  assert.match(compose, /mcp:[\s\S]*?healthcheck:[\s\S]*?127\.0\.0\.1:8010\/healthz/);
  assert.match(compose, /mcp:\n\s+condition: service_healthy/);
  assert.match(nginx, /location = \/mcp\/\$\{PDP_MCP_PATH_TOKEN\}\/healthz/);
  assert.match(nginx, /proxy_request_buffering off;/);
  assert.match(nginx, /proxy_send_timeout 3600s;/);
  assert.match(nginx, /proxy_read_timeout 3600s;/);
});

test("Windows startup and self-heal validate MCP without amplifying public-only transients", async () => {
  const startup = await load("../scripts/windows/Start-PDPOne.ps1");
  const repair = await load("../scripts/windows/Repair-PDPOneConnectivity.ps1");
  const watchdog = await load("../scripts/windows/Ensure-PDPOneMcpHealthy.ps1");
  const startupTask = await load("../scripts/windows/Register-PDPOneStartupTask.ps1");

  assert.match(startup, /local_mcp_health/);
  assert.match(startup, /public_mcp_health/);
  assert.match(startup, /mcp\/\$mcpPathToken\/healthz/);
  assert.match(startup, /Ensure-PDPOneMcpHealthy\.ps1/);
  assert.match(startup, /public_mcp_health\s*=\s*\[string\]\$connectivity\.public_mcp_health/);
  assert.match(startup, /public_mcp_health -eq "degraded"/);

  assert.match(repair, /Test-PublicPdpEndpoints/);
  assert.match(repair, /TransientConfirmDelaySeconds\s*=\s*10/);
  assert.match(repair, /public_confirmation_count/);
  assert.match(repair, /foreach \(\$confirm in 1\.\.2\)/);
  assert.match(repair, /mcp\/\$mcpPathToken\/healthz/);
  assert.match(
    repair,
    /if \(\$checks\.Health\.Success -and \$checks\.ApiHealth\.Success -and -not \$checks\.McpHealth\.Success\) \{[\s\S]*?preserving the existing Funnel route[\s\S]*?McpState "degraded"/,
  );
  assert.match(
    repair,
    /Only a repeatedly confirmed full web\/API public-route failure[\s\S]*?Restart-PDPOnePublicRoute/,
  );

  assert.match(watchdog, /\.State\.Health/);
  assert.match(watchdog, /Test-LocalMcpRoute/);
  assert.match(watchdog, /Test-PublicMcpRoute/);
  assert.match(watchdog, /PDP_PUBLIC_BASE_URL/);
  assert.match(watchdog, /confirmedPublicFailure/);
  assert.match(watchdog, /degraded_observed/);
  assert.match(watchdog, /healthy_local_public_degraded_observed/);
  assert.match(watchdog, /healthy_after_route_repair/);
  assert.doesNotMatch(watchdog, /healthy_after_public_route_repair/);
  assert.match(watchdog, /--no-build/);
  assert.match(watchdog, /--pull never/);
  assert.doesNotMatch(watchdog, /docker compose build/);
});
