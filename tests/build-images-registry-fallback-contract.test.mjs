import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const workflow = () => readFile(new URL("../.github/workflows/build-images.yml", import.meta.url), "utf8");

test("immutable image build chooses one healthy base registry before Bake", async () => {
  const text = await workflow();
  assert.match(text, /Select reachable base image registry/);
  assert.match(text, /docker\.arvancloud\.ir\/library docker\.io\/library/);
  assert.match(text, /python:3\.13-slim/);
  assert.match(text, /node:22-bookworm-slim/);
  assert.match(text, /timeout 20s docker buildx imagetools inspect/);
  assert.match(text, /PDP_DOCKER_REGISTRY=\$\{\{ steps\.base-registry\.outputs\.registry \}\}/);
  assert.equal((text.match(/uses: docker\/bake-action@v7/g) || []).length, 1);
  assert.doesNotMatch(text, /continue-on-error:\s*true/);
});
