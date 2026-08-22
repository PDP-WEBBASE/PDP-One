import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const here = path.dirname(fileURLToPath(import.meta.url));
const root = path.resolve(here, '..');
const compose = fs.readFileSync(path.join(root, 'docker-compose.yml'), 'utf8');
const hardening = fs.readFileSync(
  path.join(root, 'services', 'pdp_mcp', 'promotion_control_v3_hardening.py'),
  'utf8',
);

test('MCP persists V3 promotion state and observes Agent processing across recreation', () => {
  assert.match(
    compose,
    /queue\/processing:\/deployment-agent\/queue\/processing:ro/,
    'Agent processing queue must be visible read-only to MCP busy detection',
  );
  assert.match(
    compose,
    /queue\/promotion-v3:\/deployment-agent\/queue\/promotion-v3(?:"|\s|$)/,
    'V3 active ticket, requests, history and attestations must survive MCP recreation',
  );
  assert.match(
    compose,
    /queue\/coordinator:\/deployment-agent\/queue\/coordinator(?:"|\s|$)/,
    'shared V2/V3 promotion lease must survive MCP recreation',
  );
});

test('deployment queue emergency reserve is aligned with the durable V3 root', () => {
  assert.match(hardening, /deployment_queue\.RESERVE_PATH = promotion\.ROOT \/ "\.queue-emergency-reserve"/);
  assert.match(hardening, /configure_queue_root\(deployment_queue\.QUEUE_ROOT\)/);
  assert.match(hardening, /deployment_queue\._ensure_emergency_reserve\(\)/);
  assert.match(hardening, /"emergency_reserve_host_backed"/);
  assert.match(hardening, /promotion\.configure_queue_root = configure_queue_root/);
});

test('durability mounts do not weaken immutable Agent response boundaries', () => {
  assert.match(compose, /queue\/responses:\/deployment-agent\/queue\/responses:ro/);
  assert.match(compose, /queue\/rejected:\/deployment-agent\/queue\/rejected:ro/);
  assert.doesNotMatch(
    compose,
    /deployment-agent}\/queue:\/deployment-agent\/queue(?:"|\s|$)/,
    'do not replace narrow queue mounts with a broad writable Agent queue mount',
  );
});
