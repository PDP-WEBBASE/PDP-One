import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const here = path.dirname(fileURLToPath(import.meta.url));
const root = path.resolve(here, '..');
const server = fs.readFileSync(path.join(root, 'services', 'pdp_mcp', 'server.py'), 'utf8');
const compatibility = JSON.parse(
  fs.readFileSync(path.join(root, 'release', 'deployment-agent-compatibility.json'), 'utf8'),
);

function functionBlock(source, name) {
  const start = source.indexOf(`async def ${name}(`);
  assert.ok(start >= 0, `${name} must exist`);
  const nextTool = source.indexOf('\n\n@mcp.tool(', start);
  return source.slice(start, nextTool >= 0 ? nextTool : source.length);
}

test('stable deploy tool keeps its existing signature and reconciles the exact Agent before deployment', () => {
  const block = functionBlock(server, 'deploy_approved_release');
  assert.match(block, /async def deploy_approved_release\(commit_sha: str, deployment_id: str, preview_id: str\)/);
  assert.match(block, /commit = validate_commit\(commit_sha\)/);
  const syncIndex = block.indexOf('"sync_agent_from_exact_commit"');
  const deployIndex = block.indexOf('"deploy_approved_release"');
  assert.ok(syncIndex >= 0, 'stable deploy must submit the fixed Agent sync action');
  assert.ok(deployIndex > syncIndex, 'Agent sync must be submitted before deployment');
  assert.match(block, /await _wait_for_agent_response\(sync_request\["request_id"\]\)/);
  assert.match(block, /\{"commit_sha": commit\}/);
  assert.match(block, /"commit_sha": commit/);
});

test('self-reconcile orchestration is bounded, queue-serialized, and does not add shell/path input', () => {
  assert.match(server, /async def _wait_for_agent_response\(/);
  assert.match(server, /await asyncio\.sleep\(/);
  assert.match(server, /pending_requests/);
  assert.match(server, /sync_agent_from_exact_commit/);
  assert.doesNotMatch(server, /Invoke-Expression|\biex\b|subprocess\.|os\.system\(/i);
});

test('steady state restores all protected deployment-agent bootstrap files', () => {
  assert.equal(compatibility.schema, 'pdp-one.deployment-agent-compatibility.v1');
  assert.equal(compatibility.protocol_version, 1);
  assert.equal(Object.hasOwn(compatibility, 'migration_stage'), false);
  assert.equal(Object.hasOwn(compatibility, 'migration_note'), false);
  const protectedFiles = compatibility.bootstrap_files.map((entry) => entry.agent_file).sort();
  assert.deepEqual(protectedFiles, [
    'Deployment-Agent.Standard.ps1',
    'Invoke-PDPOneDeployment.ps1',
    'Invoke-PDPOneManagedFastDeployment.ps1',
    'Invoke-PDPOneScopedRegistryDeployment.ps1',
    'PDPOne.Common.ps1',
    'PDPOne.OperationLock.ps1',
    'PDPOne.ReleaseManifest.ps1',
    'Test-PDPOneExactCandidateCompatibility.ps1',
  ].sort());
});

test('steady state retains fixed signed Agent sync and no arbitrary shell contract', () => {
  assert.match(server, /enqueue\(\s*"sync_agent_from_exact_commit"/s);
  assert.doesNotMatch(server, /command_text|shell_command|arbitrary_path/i);
});
