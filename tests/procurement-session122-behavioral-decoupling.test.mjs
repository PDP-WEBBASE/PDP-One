import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const stableView = readFileSync("app/procurement/procurementStableViewState.ts", "utf8");
const pagination = readFileSync("app/procurement/ProcurementPaginationStableEnhancement.tsx", "utf8");
const filters = readFileSync("app/procurement/procurementV9FilterState.ts", "utf8");
const workspace = readFileSync("app/procurement/ProcurementWorkspaceV13.tsx", "utf8");

test("Session 122 stable view is projection-only and cannot infer navigation from DOM", () => {
  assert.match(stableView, /Read-only projection of the canonical React workspace state/);
  assert.doesNotMatch(stableView, /document\.addEventListener\(/);
  assert.doesNotMatch(stableView, /closest\("button"\)/);
  assert.match(workspace, /setProcurementStableViewState\(\{ top: tab, workflow \}\)/);
});

test("pagination compatibility layer is not a second Data Owner and never patches window fetch", () => {
  assert.match(pagination, /Presentation compatibility boundary only/);
  assert.match(pagination, /return null/);
  assert.doesNotMatch(pagination, /window\.fetch\s*=/);
  assert.doesNotMatch(pagination, /installPaginationFetchGuard/);
  assert.doesNotMatch(pagination, /direct-opportunities/);
  assert.doesNotMatch(pagination, /ui\/notices/);
});

test("visible all-selection is normalized to no API restriction", () => {
  assert.match(filters, /All selected = omit parameter|visible \"همه\" state is no API restriction/);
  assert.match(filters, /return sameSelection\(values, universe\) \? \[\] : \[\.\.\.values\]/);
  for (const key of ["sources", "importance", "urgency", "deadlineStatuses", "opportunityTypes", "activityDomains", "provinces"]) {
    assert.match(filters, new RegExp(`${key}: querySelection\\(current\\.${key}, FILTER_UNIVERSES\\.${key}\\)`));
  }
});

test("canonical workspace owns active-view reads and inactive views remain gated", () => {
  assert.match(workspace, /if \(mode !== \"live\" \|\| \(tab !== \"tenders\" && tab !== \"inquiries\"\)\) return/);
  assert.match(workspace, /noticeType: tab === \"tenders\" \? \"tender\" : \"inquiry\"/);
  assert.match(workspace, /if \(mode !== \"live\" \|\| tab !== \"direct\"\) return/);
  assert.match(workspace, /procurementDataClient\.staleWhileRevalidate/);
});
