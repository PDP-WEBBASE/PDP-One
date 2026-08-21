import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const here = path.dirname(fileURLToPath(import.meta.url));
const root = path.resolve(here, '..');
const read = (...parts) => fs.readFileSync(path.join(root, ...parts), 'utf8');

const queue = read('services', 'pdp_mcp', 'deployment_queue.py');
const promotion = read('services', 'pdp_mcp', 'promotion_control_v3.py');
const server = read('services', 'pdp_mcp', 'server.py');
const exact = read('services', 'pdp_mcp', 'exact_candidate_promotion_tools.py');
const v2 = read('services', 'pdp_mcp', 'deployment_coordinator.py');

test('stable legacy deploy schema is preserved but routed below the schema through V3', () => {
  assert.match(server, /async def deploy_approved_release\(commit_sha: str, deployment_id: str, preview_id: str\)/);
  assert.match(server, /return enqueue\(\s*"deploy_approved_release"/s);
  assert.match(queue, /promotion\.before_enqueue\(action, params or \{\}\)/);
  assert.match(queue, /legacy_deploy_bypass_allowed/);
  assert.match(promotion, /"legacy_deploy_bypass_allowed": False/);
  assert.match(promotion, /DEPLOY_ACTIONS = \{"deploy_approved_release", "promote_exact_candidate"\}/);
});

test('V3 and V2 share the same durable promotion lease boundary', () => {
  assert.match(promotion, /def configure_queue_root\(queue_root: Path \| str\)/);
  assert.match(promotion, /SHARED_PROMOTION_LEASE = root \/ "coordinator" \/ "promotion-lease\.json"/);
  assert.match(v2, /PROMOTION_LEASE = ROOT \/ "promotion-lease\.json"/);
  assert.match(promotion, /"schema": "pdp-one\.promotion-lease\.v3"/);
  assert.match(promotion, /ACTIVE_LEASE_HOURS/);
});

test('authoritative promotion attestation binds current main, exact PR head and workflow run ids', () => {
  assert.match(promotion, /_github_json\("branches\/main"\)/);
  assert.match(promotion, /_github_json\(f"commits\/\{commit\}\/pulls"\)/);
  assert.match(promotion, /compare\/\{main_sha\}\.\.\.\{commit\}/);
  assert.match(promotion, /behind_by != 0/);
  assert.match(promotion, /PDP One Application Boundary Governance/);
  assert.match(promotion, /PDP One CI/);
  assert.match(promotion, /Build immutable PDP One images/);
  assert.match(promotion, /"run_id": int\(run\.get\("id", 0\)\)/);
});

test('ready candidates wait durably and are re-attested only when the single lane is free', () => {
  assert.match(promotion, /"state"\] = "waiting_promotion"/);
  assert.match(promotion, /def _dispatch_waiting_candidate\(\)/);
  assert.match(promotion, /attest_commit\(commit, allow_cache=False\)/);
  assert.match(promotion, /"waiting_refresh"/);
  assert.match(promotion, /effective_priority_rank/);
});

test('stable exact promote tool allows the durable scheduler to queue rather than rejecting a busy lane', () => {
  assert.match(exact, /def _require_available_queue\(\)/);
  assert.match(exact, /queue_status = _require_available_queue\(\)/);
  assert.match(exact, /durable_promotion_queue/);
  assert.doesNotMatch(exact, /queue_status = _require_available_empty_queue\(\)[\s\S]{0,500}enqueue\(\s*"promote_exact_candidate"/);
});

test('promotion control remains public-safe and never exposes arbitrary shell execution', () => {
  assert.doesNotMatch(promotion, /subprocess|os\.system|Invoke-Expression|\biex\b|cmd\.exe\s+\/c/i);
  assert.doesNotMatch(promotion, /PDP-One-Control|PRIVATE CONTROL TOKEN|MCP_TOKEN/i);
  assert.match(promotion, /GITHUB_READ_TOKEN/);
  assert.match(promotion, /read_token_used.*bool\(GITHUB_READ_TOKEN\)/s);
});
