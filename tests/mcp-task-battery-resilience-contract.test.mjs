import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const here = path.dirname(fileURLToPath(import.meta.url));
const root = path.resolve(here, '..');
const register = fs.readFileSync(path.join(root, 'scripts', 'windows', 'Register-PDPOneStartupTask.ps1'), 'utf8');

test('recurring operational task policy is battery resilient and forces v8 reconciliation', () => {
  assert.match(register, /2026-08-28-public-edge-closed-loop-v7/);
  assert.match(register, /2026-08-28-battery-resilient-recurring-tasks-v8/);

  const criticalSettings = [
    '$mcpSettings =',
    '$mcpObservabilitySettings =',
    '$publicEdgeWatchdogSettings =',
    '$deploymentAgentWatchdogSettings =',
  ];

  for (const marker of criticalSettings) {
    const start = register.indexOf(marker);
    assert.ok(start >= 0, `missing settings block: ${marker}`);
    const line = register.slice(start, register.indexOf('\n', start));
    assert.match(line, /-AllowStartIfOnBatteries/);
    assert.match(line, /-DontStopIfGoingOnBatteries/);
  }
});
