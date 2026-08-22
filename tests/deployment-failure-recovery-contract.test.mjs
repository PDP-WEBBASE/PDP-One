import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const here = path.dirname(fileURLToPath(import.meta.url));
const root = path.resolve(here, '..');
const read = (...parts) => fs.readFileSync(path.join(root, ...parts), 'utf8');

const deployment = read('scripts', 'windows', 'Invoke-PDPOneScopedRegistryDeployment.ps1');
const recovery = read('scripts', 'windows', 'Restore-PDPOneAcceptedRelease.ps1');
const imagesWorkflow = read('.github', 'workflows', 'build-images.yml');

test('failed Runtime mutation invokes exact previous accepted-release recovery', () => {
  assert.match(deployment, /automatic_recovery_enabled = \$true/);
  assert.match(deployment, /automatic_recovery_attempted = \$true/);
  assert.match(deployment, /Restore-PDPOneAcceptedRelease\.ps1/);
  assert.match(deployment, /"-FailedDeploymentId", \$DeploymentId/);
  assert.match(deployment, /"-FailedCommit", \$CommitSha/);
  assert.match(deployment, /"-AgentRoot", \$AgentRoot/);
  assert.match(deployment, /if \(\$edgeImpact\) \{ \$recoveryArguments \+= "-RefreshConnectivityEdge" \}/);
  assert.match(deployment, /stage = "failed-recovered"/);
  assert.match(deployment, /stage = "failed-recovery-unhealthy"/);
  assert.match(deployment, /Scoped registry deployment failed, but exact previous accepted release/);
});

test('recovery is anchored to healthy accepted state and immutable exact identities', () => {
  assert.match(recovery, /last-deployment\.json/);
  assert.match(recovery, /\[string\]\$state\.status -ne "healthy"/);
  assert.match(recovery, /\$previousCommit -notmatch '\^\[0-9a-f\]\{40\}\$'/);
  assert.match(recovery, /\$previousCommit -eq \$FailedCommit/);
  assert.match(recovery, /content-\(\[0-9a-f\]\{64\}\)/);
  assert.match(recovery, /pdp-one-\(backend\|mcp\|web\):\(\[0-9a-f\]\{40\}\)/);
  assert.match(recovery, /commits\/\$previousCommit/);
  assert.match(recovery, /compare\/\$previousCommit\.\.\.\$FailedCommit/);
});

test('recovery restores source and candidate-added files without destructive mirroring', () => {
  assert.match(recovery, /robocopy\.exe \$sourceRoot\.FullName \$projectRoot \/E/);
  assert.doesNotMatch(recovery, /robocopy\.exe[^\n]*\/MIR/i);
  assert.match(recovery, /\$candidateChangedPaths/);
  assert.match(recovery, /if \(-not \(Test-Path -LiteralPath \$acceptedPath\) -and \(Test-Path -LiteralPath \$installedPath -PathType Leaf\)\)/);
  assert.match(recovery, /Remove-Item -LiteralPath \$installedPath -Force/);
});

test('recovery preserves data and refreshes Connectivity Edge only when exact failed release impacted it', () => {
  assert.match(recovery, /docker[^\n]*"up", "--detach", "db", "redis"/);
  assert.match(recovery, /if \(\$RefreshConnectivityEdge\)/);
  assert.match(recovery, /"--force-recreate", "backend", "worker", "beat", "mcp", "web"/);
  assert.doesNotMatch(recovery, /docker\s+volume\s+prune|docker\s+system\s+prune|tailscale\s+logout|rotate_mcp_token|Invoke-Expression|\biex\b/i);
  assert.doesNotMatch(recovery, /manage\.py\s+flush|dropdb|DROP\s+DATABASE/i);
});

test('recovery requires full health and preserves MCP token continuity', () => {
  assert.match(recovery, /Test-PDPOneScopedHealth\.ps1/);
  assert.match(recovery, /-Profile "full" -TimeoutSeconds 90/);
  assert.match(recovery, /Accepted previous release did not pass full recovery health/);
  assert.match(recovery, /\$tokenBefore -ne \$tokenAfter/);
  assert.match(recovery, /health = "healthy"/);
});

test('immutable image workflow smoke-tests the exact Web runtime CLI before promotion evidence can pass', () => {
  assert.match(imagesWorkflow, /name: Smoke test exact immutable Web runtime CLI/);
  assert.match(imagesWorkflow, /docker pull "\$WEB_IMAGE"/);
  assert.match(imagesWorkflow, /docker run --rm --entrypoint sh "\$WEB_IMAGE"/);
  assert.match(imagesWorkflow, /test -x \/app\/node_modules\/\.bin\/vinext/);
  assert.match(imagesWorkflow, /p\.scripts\.start\.includes\(\\"vinext start\\"\)/);
});
