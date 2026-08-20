import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const here = path.dirname(fileURLToPath(import.meta.url));
const repoRoot = path.resolve(here, '..');
const agentPath = path.join(repoRoot, 'scripts', 'windows', 'Deployment-Agent.Standard.ps1');
const agent = fs.readFileSync(agentPath, 'utf8');

const start = agent.indexOf('"run_disk_maintenance" {');
const end = agent.indexOf('"rollback_deployment" {', start);
assert.ok(start >= 0 && end > start, 'run_disk_maintenance action block must remain present');
const block = agent.slice(start, end);

test('disk maintenance ignores an empty optional deployment backup path', () => {
  assert.match(
    block,
    /\$backupPathProperty\s*=\s*\$deploymentState\.PSObject\.Properties\["backup_path"\]/,
    'maintenance must read backup_path as an optional property',
  );
  assert.match(
    block,
    /\$null\s+-ne\s+\$backupPathProperty\s+-and\s+-not\s+\[string\]::IsNullOrWhiteSpace\(\[string\]\$backupPathProperty\.Value\)\s+-and\s+\(Test-Path\s+-LiteralPath\s+\(\[string\]\$backupPathProperty\.Value\)\)/,
    'maintenance must reject null/empty/whitespace backup_path before Test-Path',
  );
  assert.doesNotMatch(
    block,
    /Test-Path\s+-LiteralPath\s+\(\[string\]\$deploymentState\.backup_path\)/,
    'maintenance must not pass the raw optional backup_path directly to Test-Path',
  );
});
