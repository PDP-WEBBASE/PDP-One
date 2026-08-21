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
const hardening = read('services', 'pdp_mcp', 'promotion_control_v3_hardening.py');
const server = read('services', 'pdp_mcp', 'server.py');
const serverProcurement = read('services', 'pdp_mcp', 'server_procurement.py');
const exact = read('services', 'pdp_mcp', 'exact_candidate_promotion_tools.py');
const v2 = read('services', 'pdp_mcp', 'deployment_coordinator.py');
const dockerfile = read('services', 'pdp_mcp', 'Dockerfile');

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

test('authoritative promotion attestation uses exact current-main effective diff, not historical PR files', () => {
  assert.match(hardening, /_github_json\("branches\/main"\)/);
  assert.match(hardening, /_github_json\(f"commits\/\{commit\}\/pulls"\)/);
  assert.match(hardening, /compare\/\{main_sha\}\.\.\.\{commit\}/);
  assert.match(hardening, /compare\.get\("files"\)/);
  assert.match(hardening, /"changed_files_source": "current-main-compare"/);
  assert.doesNotMatch(hardening, /pulls\/\{pr_number\}\/files/);
  assert.match(hardening, /behind_by != 0/);
  assert.match(hardening, /promotion\.EVIDENCE_WORKFLOWS\["boundary"\]/);
  assert.match(hardening, /promotion\.EVIDENCE_WORKFLOWS\["verify"\]/);
  assert.match(hardening, /promotion\.EVIDENCE_WORKFLOWS\["images"\]/);
  assert.match(promotion, /"boundary": "PDP One Application Boundary Governance"/);
  assert.match(promotion, /"verify": "PDP One CI"/);
  assert.match(promotion, /"images": "Build immutable PDP One images"/);
  assert.match(hardening, /"run_id": int\(run\.get\("id", 0\)\)/);
});

test('Agent request id is durably bound before the signed request becomes visible', () => {
  const bindAt = queue.indexOf('promotion.after_enqueue(action, params or {}, request_id, promotion_context)');
  const publishAt = queue.indexOf('os.replace(temporary_name, target)');
  assert.ok(bindAt >= 0, 'missing durable V3 Agent binding');
  assert.ok(publishAt >= 0, 'missing queue publication');
  assert.ok(bindAt < publishAt, 'Agent request became visible before durable V3 binding');
  assert.match(queue, /promotion_bound = True/);
  assert.match(queue, /publish_failed = getattr\(promotion, "publish_failed", None\)/);
  assert.match(hardening, /def publish_failed\(/);
  assert.match(hardening, /agent_request_publish_failed:/);
});

test('orphaned historical transport bindings become decision-required rather than endless pending', () => {
  assert.match(hardening, /ORPHAN_BINDING_SECONDS/);
  assert.match(hardening, /agent_request_binding_missing/);
  assert.match(hardening, /"decision_required"/);
});

test('GitHub reconciliation stays below the normal anonymous hourly budget while local dispatch stays responsive', () => {
  assert.match(hardening, /PDP_PROMOTION_GITHUB_RECONCILE_SECONDS/);
  assert.match(hardening, /int\(os\.getenv\("PDP_PROMOTION_GITHUB_RECONCILE_SECONDS", "180"\)\)/);
  assert.match(hardening, /GITHUB_RECONCILE_SECONDS = max\(\s*60,/s);
  assert.match(hardening, /40 reads\/hour/);
  assert.match(hardening, /now - last_github_reconcile >= GITHUB_RECONCILE_SECONDS/);
  assert.match(hardening, /promotion\._dispatch_waiting_candidate\(\)/);
  assert.match(hardening, /time\.sleep\(promotion\.DISPATCH_POLL_SECONDS\)/);
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

test('the MCP runtime loads and packages the bounded V3 hardening before tool registration', () => {
  assert.match(serverProcurement, /^import promotion_control_v3_hardening/m);
  assert.match(dockerfile, /COPY[^\n]*deployment_queue\.py[^\n]*promotion_control_v3\.py[^\n]*promotion_control_v3_hardening\.py[^\n]*exact_candidate_promotion_tools\.py/);
});

test('promotion hardening remains public-safe and never exposes arbitrary shell execution', () => {
  for (const source of [promotion, hardening]) {
    assert.doesNotMatch(source, /subprocess|os\.system|Invoke-Expression|\biex\b|cmd\.exe\s+\/c/i);
    assert.doesNotMatch(source, /PDP-One-Control|PRIVATE CONTROL TOKEN|MCP_TOKEN/i);
  }
  assert.match(promotion, /GITHUB_READ_TOKEN/);
  assert.match(hardening, /read_token_used.*bool\(promotion\.GITHUB_READ_TOKEN\)/s);
});
