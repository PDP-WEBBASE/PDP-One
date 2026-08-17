# PDP One — Hyper Turbo Analysis Lanes Specification

- Logical spec: `PDP-AUTO-HYPER-TURBO`
- Spec version: `1`
- Status: desired policy reconstructed from PR58/current chat; **live drift currently open**.

## Goal

Keep daily semantic analysis throughput ahead of roughly 4–5k incoming Tender/Inquiry records/day while clearing large historical backlog aggressively and prioritizing the newest opportunities.

## Shared execution contract

Every enabled lane:

1. reads the live active analysis run;
2. obeys backend `newest_first` / adaptive admission state rather than building a local ordering;
3. claims work atomically with a unique worker identity and lease;
4. analyzes every claimed item with the active PDP analysis Context;
5. returns/imports one result per claimed item with claim/content/context identity intact;
6. imports as AI Draft requiring human review;
7. claims again only after successful import/no unresolved items;
8. never publishes/selects/creates final business or financial records;
9. never changes global Context/settings/tokens/runtime deployment.

## Lane roles

### Lane 1 — primary
- Worker: `pdp-hyper-lane-1`
- May start an incremental run if **no active run exists**.
- If remaining < 1000: maximum 2 claims per scheduled execution.
- Otherwise: maximum 4 claims.
- Historical claim request: limit 500; lease 3600 seconds.

### Lane 2
- Worker: `pdp-hyper-lane-2`
- Runs only while remaining >=1000.
- Max 4 claims; historical limit 500 / lease 3600.

### Lane 3
- Worker: `pdp-hyper-lane-3`
- Desired threshold remaining >=5000.
- Max 4 claims.
- **Live bootstrap state: disabled.**

### Lane 4
- Worker: `pdp-hyper-lane-4`
- Threshold remaining >=5000.
- Max 4 claims.
- Live bootstrap state: enabled.

### Lane 5
- Worker: `pdp-hyper-lane-5`
- Desired threshold remaining >=10000.
- Max 4 claims.
- **Live bootstrap state: disabled.**

### Lane 6
- Worker: `pdp-hyper-lane-6`
- Threshold remaining >=10000.
- Max 4 claims.
- Live bootstrap state: enabled.

### Lane 7
- Worker: `pdp-hyper-lane-7`
- Threshold remaining >=20000.
- Max 4 claims.
- Live bootstrap state: enabled.

### Lane 8
- Worker: `pdp-hyper-lane-8`
- Threshold remaining >=20000.
- Max 4 claims.
- Live bootstrap state: enabled.

## Desired adaptive lane count

- >=20k: lanes 1–8
- 10k–19,999: lanes 1–6
- 5k–9,999: lanes 1–4
- 1k–4,999: lanes 1–2
- <1k: lane 1 reduced

This desired schedule requires a separate governor/change session to enforce dynamically. Routine lane execution must **not** enable/disable sibling tasks by itself.

## Semantic-analysis policy

Historical prompt conventions used compact result fields and marked deeper-analysis candidates for recommended/urgent/ambiguous/needs-information/high-score cases. The exact result schema must come from the active Context/API contract at run time.

Keywords remain context/search guidance; no deterministic local scoring replacement.

## Failure policy

- If Context/run cannot be read: stop risky write and report context failure.
- If an import has unresolved items: do not advance to the next claim as though successful.
- Never cancel/restart a healthy active run merely to clear a lane error.
- Never use stale historical run counts to decide current lane threshold.

## Drift protocol

Before any live lane mutation:

- require `PDPONE START`;
- read current run and backlog;
- read all live lane enabled/schedule/prompt state;
- read active Session Issues/open PRs;
- compare with this spec;
- determine whether drift is intentional;
- change only after conflict/intent is clear;
- verify live state after mutation;
- update this spec/registry/session/timeline if policy changes.
