import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';

const ci = readFileSync('.github/workflows/ci.yml', 'utf8');
const bake = readFileSync('infra/docker/pdp-images-bake.hcl', 'utf8');

function caseBlock(pattern) {
  const start = ci.indexOf(pattern);
  assert.notEqual(start, -1, `missing CI case pattern: ${pattern}`);
  const end = ci.indexOf(';;', start);
  assert.notEqual(end, -1, `missing CI case terminator: ${pattern}`);
  return ci.slice(start, end);
}

test('required CI check identities remain stable', () => {
  assert.match(ci, /^name: PDP One CI$/m);
  assert.match(ci, /^  verify:$/m);
  assert.match(ci, /^    name: Windows PowerShell 5\.1 compatibility$/m);
});

test('contract-only Node changes stay on the fast path', () => {
  const contractBlock = caseBlock('tests/*-contract.test.mjs)');
  assert.match(contractBlock, /run_fast_contracts=true/);
  assert.doesNotMatch(contractBlock, /run_node=true/);
  assert.match(ci, /node --test tests\/\*-contract\.test\.mjs/);
});

test('procurement-only backend changes avoid unrelated core tests', () => {
  const procurementBlock = caseBlock('backend/procurement/*)');
  assert.match(procurementBlock, /run_backend_python=true/);
  assert.match(procurementBlock, /run_django_procurement=true/);
  assert.doesNotMatch(procurementBlock, /run_django_core=true/);

  const procurementIndex = ci.indexOf('backend/procurement/*)');
  const backendFallbackIndex = ci.indexOf('backend/*)');
  assert.ok(procurementIndex < backendFallbackIndex, 'specific procurement classification must precede the fail-safe backend fallback');
});

test('core and unknown backend changes fail safe to broad Django coverage', () => {
  for (const pattern of ['backend/core/*)', 'backend/*)']) {
    const block = caseBlock(pattern);
    assert.match(block, /run_django_core=true/);
    assert.match(block, /run_django_procurement=true/);
  }
});

test('MCP-only changes use focused Python tests without forcing Django suites', () => {
  const mcpBlock = caseBlock('services/pdp_mcp/*)');
  assert.match(mcpBlock, /run_backend_python=true/);
  assert.match(mcpBlock, /run_mcp_tests=true/);
  assert.doesNotMatch(mcpBlock, /run_django_core=true/);
  assert.doesNotMatch(mcpBlock, /run_django_procurement=true/);
  assert.match(ci, /python -m unittest discover -s services\/pdp_mcp -p 'test_\*\.py' -v/);
});

test('shared CI or compose changes still run full backend impact coverage', () => {
  const sharedBlock = caseBlock("docker-compose.yml|.github/workflows/ci.yml)");
  assert.match(sharedBlock, /run_django_core=true/);
  assert.match(sharedBlock, /run_django_procurement=true/);
  assert.match(sharedBlock, /run_mcp_tests=true/);
});

test('Django test labels are selected dynamically from impact flags', () => {
  assert.match(ci, /labels=\(\)/);
  assert.match(ci, /labels\+=\(core\.tests\)/);
  assert.match(ci, /labels\+=\(procurement\.tests\)/);
  assert.match(ci, /python backend\/manage\.py test "\$\{labels\[@\]\}" -v 2/);
});

test('remote BuildKit cache remains enabled independently per component', () => {
  for (const component of ['backend', 'mcp', 'web']) {
    assert.match(bake, new RegExp(`cache-from = \\["type=gha,scope=pdp-one-${component}"\\]`));
    assert.match(bake, new RegExp(`cache-to\\s+= \\["type=gha,mode=max,scope=pdp-one-${component}"\\]`));
  }
});
