import fs from "node:fs";
import assert from "node:assert/strict";
import test from "node:test";

const workspace = fs.readFileSync("app/procurement/ProcurementWorkspaceV13.tsx", "utf8");

test("shared procurement pagination exposes standard numbered navigation", () => {
  assert.match(workspace, /pageTokens/);
  assert.match(workspace, /aria-current=\{token === page \? "page"/);
  assert.match(workspace, />صفحه قبل<\/button>/);
  assert.match(workspace, />صفحه بعد<\/button>/);
  assert.match(workspace, />…<\/span>/);
});

test("shared pagination preserves page size and supports compact manual jump", () => {
  assert.match(workspace, /<option value=\{30\}>۳۰<\/option>/);
  assert.match(workspace, /<option value=\{50\}>۵۰<\/option>/);
  assert.match(workspace, /<option value=\{100\}>۱۰۰<\/option>/);
  assert.match(workspace, /برو به صفحه/);
  assert.match(workspace, /type="number"/);
  assert.match(workspace, /submitJump/);
  assert.doesNotMatch(workspace, /شماره صفحه را به‌صورت عدد صحیح وارد کنید/);
});


test("notice exact pagination metadata is asynchronous and separate from the bounded hot path", () => {
  assert.match(workspace, /pagination-metadata/);
  assert.match(workspace, /noticeExactCount/);
  assert.match(workspace, /noticeLoading\) return/);
  assert.match(workspace, /count=\{noticeExactCount \?\? noticeCount\}/);
});
