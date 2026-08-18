import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";


test("PDP One builds immutable images in GitHub and never builds on the laptop", async () => {
  const workflow = await readFile(new URL("../.github/workflows/build-images.yml", import.meta.url), "utf8");
  const managed = await readFile(new URL("../scripts/windows/Invoke-PDPOneManagedFastDeployment.ps1", import.meta.url), "utf8");
  const registryDeploy = await readFile(new URL("../scripts/windows/Invoke-PDPOneRegistryFastDeployment.ps1", import.meta.url), "utf8");
  const compose = await readFile(new URL("../docker-compose.yml", import.meta.url), "utf8");

  assert.match(workflow, /packages:\s*write/);
  assert.match(workflow, /docker\/build-push-action@v6/);
  assert.match(workflow, /ghcr\.io\/pdp-webbase\/pdp-one-(backend|mcp|web)/);
  assert.match(workflow, /github\.event\.pull_request\.head\.sha \|\| github\.sha/);
  assert.match(workflow, /cache-to:\s*type=gha/);
  assert.match(managed, /Invoke-PDPOneRegistryFastDeployment\.ps1/);
  assert.match(registryDeploy, /local_image_build_performed = \$false/);
  assert.match(registryDeploy, /-Command "docker" -Arguments @\("pull", \$image\)/);
  assert.doesNotMatch(registryDeploy, /-Command "docker" -Arguments @\("compose", "build"/);
  assert.doesNotMatch(compose, /^\s+build:/m);
});


test("OCI revision labels are parsed without a quoted Go-template key on Windows PowerShell", async () => {
  const registryDeploy = await readFile(new URL("../scripts/windows/Invoke-PDPOneRegistryFastDeployment.ps1", import.meta.url), "utf8");

  assert.match(registryDeploy, /--format '\{\{json \.Config\.Labels\}\}'/);
  assert.match(registryDeploy, /ConvertFrom-Json/);
  assert.match(registryDeploy, /PSObject\.Properties\['org\.opencontainers\.image\.revision'\]/);
  assert.doesNotMatch(registryDeploy, /index \.Config\.Labels/);
});


test("development-fast deployment performs only bounded connectivity recovery before public-health failure", async () => {
  const registryDeploy = await readFile(new URL("../scripts/windows/Invoke-PDPOneRegistryFastDeployment.ps1", import.meta.url), "utf8");
  const compose = await readFile(new URL("../docker-compose.yml", import.meta.url), "utf8");

  assert.match(registryDeploy, /Repair-PDPOneConnectivity\.ps1/);
  assert.match(registryDeploy, /-RepairAttempts 1/);
  assert.match(registryDeploy, /-DnsPublicationTimeoutSeconds 90/);
  assert.match(registryDeploy, /connectivity_repair_attempted/);
  assert.match(registryDeploy, /connectivity_repair_succeeded/);
  assert.match(registryDeploy, /Short public health check failed after bounded connectivity recovery/);

  assert.match(compose, /post_start:/);
  assert.match(compose, /pdp-funnel-dns-bootstrap-v1\.done/);
  assert.match(compose, /funnel reset/);
  assert.match(compose, /funnel --bg --yes 80/);
  assert.match(compose, /touch "\$sentinel"/);
  assert.doesNotMatch(compose, /tailscale\s+logout/);
  assert.doesNotMatch(compose, /tailscale\s+down/);
});


test("PDP One caps cache, rotates logs, retains active, previous, and in-flight images, and disables Kubernetes", async () => {
  const guard = await readFile(new URL("../scripts/windows/Invoke-PDPOneDiskGuard.ps1", import.meta.url), "utf8");
  const compose = await readFile(new URL("../docker-compose.yml", import.meta.url), "utf8");
  const policy = await readFile(new URL("../scripts/windows/Ensure-PDPOneRancherPolicy.ps1", import.meta.url), "utf8");
  const startup = await readFile(new URL("../scripts/windows/Start-PDPOne.ps1", import.meta.url), "utf8");

  assert.match(guard, /BuildCacheBudgetGB = 2/);
  assert.match(guard, /--keep-storage/);
  assert.match(guard, /active_previous_and_inflight_commit/);
  assert.match(guard, /Get-PDPOneInFlightCommit/);
  assert.doesNotMatch(guard, /image", "prune", "--all"/);
  assert.doesNotMatch(guard, /volume\s+prune/i);
  assert.match(compose, /driver: local/);
  assert.match(compose, /max-size: "10m"/);
  assert.match(compose, /max-file: "3"/);
  assert.match(policy, /--kubernetes-enabled=false/);
  assert.match(policy, /kubernetes_enabled_after/);
  assert.match(startup, /Ensure-PDPOneRancherPolicy\.ps1/);
});
