import fs from 'node:fs';
import test from 'node:test';
import assert from 'node:assert/strict';

const observer = fs.readFileSync('scripts/windows/Observe-PDPOneMcpRoute.ps1', 'utf8');
const taskPolicy = fs.readFileSync('scripts/windows/Register-PDPOneStartupTask.ps1', 'utf8');
const diagnosticsTools = fs.readFileSync('services/pdp_mcp/route_diagnostics_tools.py', 'utf8');
const server = fs.readFileSync('services/pdp_mcp/server.py', 'utf8');
const mcpDockerfile = fs.readFileSync('services/pdp_mcp/Dockerfile', 'utf8');

test('route observer is passive and checkpoint based', () => {
  for (const id of ['CP-01', 'CP-02', 'CP-03', 'CP-04', 'CP-05', 'CP-06', 'CP-07', 'CP-08', 'CP-09', 'CP-10', 'CP-11', 'CP-12', 'CP-13', 'CP-14']) {
    assert.match(observer, new RegExp(id));
  }
  assert.match(observer, /Set-Location \$ProjectRoot/);
  assert.match(observer, /passive_only\s*=\s*\$true/);
  assert.match(observer, /repair_actions\s*=\s*0/);
  assert.match(observer, /active_incident_started_at/);
  assert.match(observer, /root_cause_classification/);
  assert.match(observer, /pre_incident_minutes=15/);
  assert.match(observer, /post_recovery_minutes=10/);
  assert.doesNotMatch(observer, /funnel\s+reset/i);
  assert.doesNotMatch(observer, /--force-recreate/i);
  assert.doesNotMatch(observer, /docker\s+(?:compose\s+)?restart/i);
  assert.doesNotMatch(observer, /Rotate-PDPOneMcpToken/i);
});

test('observer never persists the MCP path token', () => {
  assert.match(observer, /tokenFingerprint/);
  assert.doesNotMatch(observer, /token\s*=\s*\$token/);
  assert.match(observer, /secrets_included\s*=\s*\$false/);
});

test('scheduled task runs passive observer once per minute', () => {
  assert.match(taskPolicy, /PDP One MCP Route Observability/);
  assert.match(taskPolicy, /Observe-PDPOneMcpRoute\.ps1/);
  assert.match(taskPolicy, /RepetitionInterval \(New-TimeSpan -Minutes 1\)/);
});

test('MCP exposes bounded read-only route evidence tools', () => {
  assert.match(diagnosticsTools, /get_mcp_route_diagnostics/);
  assert.match(diagnosticsTools, /get_mcp_incident_report/);
  assert.match(diagnosticsTools, /readOnlyHint=True/);
  assert.match(diagnosticsTools, /destructiveHint=False/);
  assert.match(diagnosticsTools, /timedelta\(minutes=15\)/);
  assert.match(diagnosticsTools, /timedelta\(minutes=10\)/);
  assert.match(diagnosticsTools, /max_samples_returned/);
  assert.match(server, /register_route_diagnostics_tools/);
});

test('MCP runtime image packages every observability module imported at startup', () => {
  assert.match(mcpDockerfile, /COPY[^\n]*server_core\.py/);
  assert.match(mcpDockerfile, /COPY[^\n]*route_diagnostics_tools\.py/);
  assert.match(mcpDockerfile, /CMD \["python", "server_procurement\.py"\]/);
});
