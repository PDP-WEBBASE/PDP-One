import assert from 'node:assert/strict';
import fs from 'node:fs';
import test from 'node:test';

const dockerfile = fs.readFileSync('services/pdp_mcp/Dockerfile', 'utf8');
const server = fs.readFileSync('services/pdp_mcp/server_procurement.py', 'utf8');
const policy = fs.readFileSync('services/pdp_mcp/promotion_control_v3_short_lane.py', 'utf8');

test('MCP image and server activate short critical promotion lane policy', () => {
  assert.match(dockerfile, /promotion_control_v3_short_lane\.py/);
  assert.match(server, /import promotion_control_v3_short_lane/);
});

test('short lane contract keeps long acceptance post-merge and non-blocking', () => {
  assert.match(policy, /extended_acceptance_blocks_lane/);
  assert.match(policy, /extended_acceptance_phase/);
  assert.match(policy, /post_merge/);
  assert.match(policy, /lane_hold_violation/);
  assert.match(policy, /do_not_wait_for_extended_sla_soak_in_lane/);
  assert.match(policy, /exact_source_cumulative/);
});
