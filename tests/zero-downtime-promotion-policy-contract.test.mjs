import assert from 'node:assert/strict';
import fs from 'node:fs';
import test from 'node:test';

const policy = JSON.parse(fs.readFileSync('release/zero-downtime-promotion-v1.json', 'utf8'));

test('zero-downtime runtime policy preserves the approved V1 boundaries', () => {
  assert.equal(policy.schema, 'pdp-one.zero-downtime-promotion.v1');
  assert.equal(policy.strategy, 'temporary_candidate_nginx_graceful_switch_v1');
  assert.equal(policy.stabilization_seconds, 30);
  assert.equal(policy.candidate_readiness_required, true);
  assert.equal(policy.mcp_continuity_required, true);
  assert.equal(policy.api_continuity_required, true);
  assert.equal(policy.nginx_restart_allowed_for_normal_application_promotion, false);
  assert.equal(policy.tailscale_restart_allowed_for_normal_application_promotion, false);
  assert.equal(policy.kubernetes_required, false);
  assert.equal(policy.credential_rotation_allowed, false);
  assert.equal(policy.destructive_database_action_allowed, false);
  assert.equal(policy.docker_volume_reset_allowed, false);
});
