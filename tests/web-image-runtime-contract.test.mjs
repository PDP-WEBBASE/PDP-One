import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

test("Web image contains only the pruned Vinext runtime surface", async () => {
  const dockerfile = await readFile(
    new URL("../infra/docker/web.Dockerfile", import.meta.url),
    "utf8",
  );

  assert.match(dockerfile, /FROM .* AS build/);
  assert.match(dockerfile, /FROM .* AS runtime/);
  assert.match(dockerfile, /npm prune --omit=dev/);
  assert.match(dockerfile, /npm install --no-save --omit=dev/);

  for (const runtimePackage of [
    "vinext@0.0.50",
    "vite@8.0.13",
    "wrangler@4.92.0",
    "@cloudflare/vite-plugin@1.37.1",
    "@vitejs/plugin-react@6.0.2",
    "@vitejs/plugin-rsc@0.5.26",
  ]) {
    assert.ok(
      dockerfile.includes(runtimePackage),
      `missing pinned Web runtime package: ${runtimePackage}`,
    );
  }

  assert.doesNotMatch(dockerfile, /COPY --from=build \/app \.\//);
  assert.doesNotMatch(dockerfile, /COPY --from=build \/app \/app/);
  assert.doesNotMatch(dockerfile, /COPY --from=build \/app\/(app|components|tests|scripts)\b/);

  for (const runtimePath of [
    "node_modules",
    "dist",
    "public",
    ".openai",
    "build",
    "worker",
    "vite.config.ts",
  ]) {
    assert.ok(
      dockerfile.includes(`COPY --from=build /app/${runtimePath}`),
      `missing required Web runtime path: ${runtimePath}`,
    );
  }

  assert.match(dockerfile, /pdp-build\.json/);
  assert.match(dockerfile, /CMD \["npm", "run", "start"/);
});
