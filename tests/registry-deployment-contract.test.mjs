import assert from "node:assert/strict";
import { mkdtemp, mkdir, readFile, rm, writeFile } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import test from "node:test";

import { computeComponentFingerprints } from "../scripts/ci/component-fingerprints.mjs";


test("PDP One publishes or reuses immutable content-addressed component images on one GitHub runner", async () => {
  const workflow = await readFile(new URL("../.github/workflows/build-images.yml", import.meta.url), "utf8");
  const bake = await readFile(new URL("../infra/docker/pdp-images-bake.hcl", import.meta.url), "utf8");
  const managed = await readFile(new URL("../scripts/windows/Invoke-PDPOneManagedFastDeployment.ps1", import.meta.url), "utf8");
  const scopedDeploy = await readFile(new URL("../scripts/windows/Invoke-PDPOneScopedRegistryDeployment.ps1", import.meta.url), "utf8");
  const compose = await readFile(new URL("../docker-compose.yml", import.meta.url), "utf8");
  const mode = JSON.parse(await readFile(new URL("../release/component-image-mode.json", import.meta.url), "utf8"));
  const contexts = JSON.parse(await readFile(new URL("../release/component-contexts.json", import.meta.url), "utf8"));
  const dockerignore = await readFile(new URL("../.dockerignore", import.meta.url), "utf8");

  assert.match(workflow, /pull_request:\s*\n\s+paths-ignore:/);
  assert.doesNotMatch(workflow, /\n\s+push:\s*\n\s+branches:\s*\[main\]/);
  assert.doesNotMatch(workflow, /-\s+"release\/\*\*"/);
  assert.match(workflow, /group:\s*pdp-one-images-pr-\$\{\{ github\.event\.pull_request\.number \}\}/);
  assert.match(workflow, /cancel-in-progress:\s*true/);
  assert.match(workflow, /RELEASE_SHA:\s*\$\{\{ github\.event\.pull_request\.head\.sha \}\}/);
  assert.match(workflow, /component-fingerprints\.mjs --github-output/);
  assert.match(workflow, /docker buildx imagetools inspect "\$image"/);
  assert.match(workflow, /action="reuse"/);
  assert.match(workflow, /targets=\(\)/);
  assert.match(workflow, /targets:\s*\$\{\{ steps\.plan\.outputs\.targets \}\}/);
  assert.match(workflow, /if:\s*steps\.plan\.outputs\.targets != ''/);
  assert.match(workflow, /docker\/bake-action@v7/);
  assert.match(workflow, /source:\s*\./);
  assert.match(workflow, /files:\s*\.\/infra\/docker\/pdp-images-bake\.hcl/);
  assert.match(workflow, /push:\s*true/);
  assert.match(workflow, /provenance:\s*false/);
  assert.match(workflow, /DOCKER_BUILD_RECORD_UPLOAD:\s*"false"/);
  assert.doesNotMatch(workflow, /matrix:\s*\n/);

  assert.match(bake, /group "default"\s*\{[\s\S]*targets = \["backend", "mcp", "web"\]/);
  assert.match(bake, /pdp-one-backend:content-\$\{BACKEND_FINGERPRINT\}/);
  assert.match(bake, /pdp-one-mcp:content-\$\{MCP_FINGERPRINT\}/);
  assert.match(bake, /pdp-one-web:content-\$\{WEB_FINGERPRINT\}/);
  assert.equal((bake.match(/"org\.opencontainers\.image\.revision"\s+= RELEASE_SHA/g) || []).length, 3);
  assert.equal((bake.match(/"io\.pdpone\.component\.fingerprint"/g) || []).length, 3);
  assert.equal((bake.match(/"io\.pdpone\.component"/g) || []).length, 3);
  assert.match(bake, /cache-from = \["type=gha,scope=pdp-one-backend"\]/);
  assert.match(bake, /cache-to\s+= \["type=gha,mode=max,scope=pdp-one-web"\]/);
  assert.match(bake, /PDP_BUILD_ID\s+= "content-\$\{WEB_FINGERPRINT\}"/);

  assert.equal(mode.mode, "content-addressed-v1");
  assert.ok(contexts.components.web.exclude_prefixes.includes("scripts/ci/"));
  assert.match(dockerignore, /^release$/m);
  assert.match(dockerignore, /^scripts\/ci$/m);
  assert.match(dockerignore, /^scripts\/windows$/m);
  assert.match(dockerignore, /^backend$/m);
  assert.match(dockerignore, /^services$/m);

  assert.match(managed, /Invoke-PDPOneScopedRegistryDeployment\.ps1/);
  assert.match(scopedDeploy, /Get-PDPOneComponentFingerprint/);
  assert.match(scopedDeploy, /Get-PDPOneComponentImageReference/);
  assert.match(scopedDeploy, /Write-PDPOneReleaseManifest/);
  assert.match(scopedDeploy, /local_image_build_performed = \$false/);
  assert.doesNotMatch(scopedDeploy, /-Command "docker" -Arguments @\("compose", "build"/);
  assert.doesNotMatch(compose, /^\s+build:/m);
});


test("component fingerprinting ignores build-only web files and changes only the affected component", async () => {
  const root = await mkdtemp(path.join(os.tmpdir(), "pdp-component-fingerprint-"));
  try {
    for (const directory of ["backend", "services/pdp_mcp", "app", "release", "scripts/ci", "scripts/windows", "tests"]) {
      await mkdir(path.join(root, directory), { recursive: true });
    }
    await writeFile(path.join(root, "backend", "a.py"), "backend-v1\n");
    await writeFile(path.join(root, "services", "pdp_mcp", "a.py"), "mcp-v1\n");
    await writeFile(path.join(root, "app", "page.tsx"), "web-v1\n");
    await writeFile(path.join(root, "scripts", "ci", "planner.mjs"), "ignored-build-tool-v1\n");
    await writeFile(path.join(root, "scripts", "windows", "host.ps1"), "ignored-host-tool-v1\n");
    await writeFile(path.join(root, "tests", "contract.test.mjs"), "ignored-test-v1\n");
    await writeFile(path.join(root, "release", "component-contexts.json"), JSON.stringify({
      schema: "pdp-one.component-contexts.v1",
      components: {
        backend: { root: "backend", exclude_prefixes: [], exclude_files: [], exclude_suffixes: [], exclude_name_prefixes: [] },
        mcp: { root: "services/pdp_mcp", exclude_prefixes: [], exclude_files: [], exclude_suffixes: [], exclude_name_prefixes: [] },
        web: {
          root: ".",
          exclude_prefixes: ["backend/", "services/", "release/", "scripts/windows/", "scripts/ci/", "tests/"],
          exclude_files: [],
          exclude_suffixes: [".md", ".bat"],
          exclude_name_prefixes: [".env"],
        },
      },
    }, null, 2));

    const first = await computeComponentFingerprints(root);
    await writeFile(path.join(root, "scripts", "ci", "planner.mjs"), "ignored-build-tool-v2\n");
    const afterBuildTool = await computeComponentFingerprints(root);
    assert.deepEqual(afterBuildTool, first);

    await writeFile(path.join(root, "app", "page.tsx"), "web-v2\n");
    const afterWeb = await computeComponentFingerprints(root);
    assert.equal(afterWeb.backend, first.backend);
    assert.equal(afterWeb.mcp, first.mcp);
    assert.notEqual(afterWeb.web, first.web);
  } finally {
    await rm(root, { recursive: true, force: true });
  }
});


test("PR governance cancels superseded runs and keeps CI change-aware without changing required checks", async () => {
  const ci = await readFile(new URL("../.github/workflows/ci.yml", import.meta.url), "utf8");
  const boundary = await readFile(new URL("../.github/workflows/pdp-memory-governance.yml", import.meta.url), "utf8");

  assert.match(ci, /on:\s*\n\s+pull_request:/);
  assert.doesNotMatch(ci, /\n\s+push:\s*\n\s+branches:\s*\[main\]/);
  assert.match(ci, /group:\s*pdp-one-ci-pr-\$\{\{ github\.event\.pull_request\.number \}\}/);
  assert.match(ci, /cancel-in-progress:\s*true/);
  assert.match(ci, /\n\s+verify:\s*\n/);
  assert.match(ci, /name:\s*Windows PowerShell 5\.1 compatibility/);
  assert.match(ci, /name:\s*Classify PR change scope/);
  assert.match(ci, /RUN_NODE=/);
  assert.match(ci, /RUN_BACKEND_PYTHON=/);
  assert.match(ci, /RUN_DJANGO_CORE=/);
  assert.match(ci, /RUN_DJANGO_PROCUREMENT=/);
  assert.match(ci, /RUN_MCP_TESTS=/);
  assert.match(ci, /RUN_WINDOWS_HELPERS=/);
  assert.match(ci, /RUN_PREVIEW=/);
  assert.match(ci, /RUN_CONNECTOR_PACKAGES=/);
  assert.match(ci, /if:\s*env\.RUN_BACKEND_PYTHON == 'true'/);
  assert.match(ci, /if:\s*env\.RUN_DJANGO_CORE == 'true' \|\| env\.RUN_DJANGO_PROCUREMENT == 'true'/);
  assert.match(ci, /if:\s*env\.RUN_MCP_TESTS == 'true'/);
  assert.match(ci, /if:\s*env\.RUN_WINDOWS_HELPERS == 'true'/);
  assert.match(ci, /if:\s*env\.RUN_CONNECTOR_PACKAGES == 'true' && success\(\)/);
  assert.match(ci, /if:\s*steps\.frontend_lint\.outcome == 'failure'/);
  assert.match(ci, /steps\.python_compile\.outcome == 'failure'/);
  assert.match(ci, /steps\.migration_check\.outcome == 'failure'/);
  assert.match(ci, /steps\.mcp_tests\.outcome == 'failure'/);
  assert.match(ci, /steps\.backend_tests\.outcome == 'failure'/);
  assert.match(ci, /retention-days:\s*3/);

  assert.match(boundary, /group:\s*pdp-one-public-boundary-pr-\$\{\{ github\.event\.pull_request\.number \}\}/);
  assert.match(boundary, /cancel-in-progress:\s*true/);
  assert.match(boundary, /\n\s+public-boundary:\s*\n/);
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
  assert.match(compose, /\$\$\(\(attempt \+ 1\)\)/);
  assert.match(compose, /touch "\$\$sentinel"/);
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
  assert.match(guard, /active_previous_and_inflight_release_manifests/);
  assert.match(guard, /Get-PDPOneManifestImageReferences/);
  assert.match(guard, /Read-PDPOneDeploymentOperation/);
  assert.match(guard, /active_release_manifest/);
  assert.match(guard, /previous_release_manifest/);
  assert.match(guard, /content-\[0-9a-f\]\{64\}/);
  assert.match(guard, /Add-PDPOneCommitImageReferences/);
  assert.doesNotMatch(guard, /image", "prune", "--all"/);
  assert.doesNotMatch(guard, /volume\s+prune/i);
  assert.match(compose, /driver: local/);
  assert.match(compose, /max-size: "10m"/);
  assert.match(compose, /max-file: "3"/);
  assert.match(policy, /--kubernetes-enabled=false/);
  assert.match(policy, /kubernetes_enabled_after/);
  assert.match(startup, /Ensure-PDPOneRancherPolicy\.ps1/);
});
