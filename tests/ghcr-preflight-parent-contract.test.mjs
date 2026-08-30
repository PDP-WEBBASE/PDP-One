import fs from "node:fs";
import test from "node:test";
import assert from "node:assert/strict";

const helper = fs.readFileSync("scripts/windows/Test-PDPOneGhcrCredential.ps1", "utf8");
const managed = fs.readFileSync("scripts/windows/Invoke-PDPOneManagedFastDeployment.ps1", "utf8");

test("GHCR preflight failures preserve parent exit-code/report handling on Windows PowerShell 5.1", () => {
  const catchBlock = helper.match(/} catch \{[\s\S]*?\n} finally \{/)?.[0] || "";
  assert.ok(catchBlock, "expected GHCR preflight catch/finally block");
  assert.doesNotMatch(catchBlock, /Write-Error/, "expected preflight failure must not be emitted on the Error stream");
  assert.match(catchBlock, /Write-Output \$report\.error/);
  assert.match(catchBlock, /exit 1/);

  assert.match(managed, /\$credentialPreflightScript\s*=\s*Join-Path \$PSScriptRoot "Test-PDPOneGhcrCredential\.ps1"/);
  assert.match(managed, /\$credentialOutput\s*=\s*@\(& powershell\.exe[\s\S]*?-File \$credentialPreflightScript/);
  assert.match(managed, /\$credentialExitCode\s*=\s*\$LASTEXITCODE/);
  assert.match(managed, /if \(\$credentialExitCode -ne 0\)[\s\S]*?\$failureReportPath/);
  assert.match(managed, /stage = "ghcr-credential-preflight"/);
});
