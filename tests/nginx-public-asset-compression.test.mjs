import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const read = (path) => readFile(new URL(`../${path}`, import.meta.url), "utf8");

test("nginx compresses first-load text assets on the public edge", async () => {
  const nginx = await read("infra/nginx/default.conf.template");

  assert.match(nginx, /gzip on;/);
  assert.match(nginx, /gzip_vary on;/);
  assert.match(nginx, /gzip_proxied any;/);
  assert.match(nginx, /gzip_comp_level 5;/);
  assert.match(nginx, /gzip_min_length 1024;/);
  for (const mime of [
    "text/css",
    "text/javascript",
    "application/javascript",
    "application/json",
    "application/manifest+json",
    "image/svg+xml",
  ]) {
    assert.ok(nginx.includes(mime), `gzip_types must include ${mime}`);
  }
});

test("asset cache remains immutable while compression is enabled", async () => {
  const nginx = await read("infra/nginx/default.conf.template");
  assert.match(
    nginx,
    /location \/assets\/ \{[\s\S]*Cache-Control "public, max-age=31536000, immutable"/,
  );
});
