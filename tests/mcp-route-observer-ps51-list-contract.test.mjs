import fs from 'node:fs';
import assert from 'node:assert/strict';

const script = fs.readFileSync('scripts/windows/Observe-PDPOneMcpRoute.ps1', 'utf8');

assert.match(script, /\$checksArray\s*=\s*\$checks\.ToArray\(\)/, 'observer must materialize the generic List[object] through ToArray() for Windows PowerShell 5.1');
assert.doesNotMatch(script, /checkpoints\s*=\s*@\(\$checks\)/, 'observer must not array-subexpress Generic.List[object] in sample payloads');
assert.doesNotMatch(script, /latest_checkpoints\s*=\s*@\(\$checks\)/, 'observer must not array-subexpress Generic.List[object] in incident payloads');
assert.match(script, /checkpoints\s*=\s*\$checksArray/, 'sample payload must use the PS5.1-safe checkpoint array');
assert.match(script, /latest_checkpoints\s*=\s*\$checksArray/, 'incident payload must use the PS5.1-safe checkpoint array');
