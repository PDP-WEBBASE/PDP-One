import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

test("release manifest accepts host-only releases with zero changed application services", async () => {
  const helper = await readFile(new URL("../scripts/windows/PDPOne.ReleaseManifest.ps1", import.meta.url), "utf8");
  assert.match(
    helper,
    /\[Parameter\(Mandatory = \$true\)\]\[AllowEmptyCollection\(\)\]\[string\[\]\]\$ChangedServices/,
  );
  assert.match(helper, /changed_in_release = \(\$component -in \$ChangedServices\)/);
});
