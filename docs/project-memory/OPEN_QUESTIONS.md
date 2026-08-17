# PDP One — Open Questions

These are live questions requiring intentional future resolution. Historical unknowns that cannot be answered from current sources are separately preserved in `GAPS_AND_UNVERIFIED.md`.

## OQ-001 — Why are Hyper Turbo lanes 3 and 5 disabled?

Current live state has lanes 3/5 disabled while desired PR58 >=20k policy described eight lanes and current backlog is >20k.

Possible explanations include deliberate throttling, task failure/auto-disable, manual change or an intentional later decision not yet recorded in GitHub.

Do not guess. Resolve in a separate activated Automation session by reading task history/current state and user intent.

## OQ-002 — Disposition of old PR45 / PR46

Both remain open on old bases. Decide later whether to:

- close as fully superseded;
- extract still-useful parts into a new branch;
- explicitly document a later accepted equivalent implementation.

Never merge old heads directly without reconciling modern main.

## OQ-003 — Should Transfer v10 binary/source archive be stored as a GitHub Release asset?

All 69 files are inventoried and their knowledge is ingested. The original package is verified by exact SHA but the large binary résumé/ZIP are not duplicated in this docs branch.

A future storage-policy decision may add an immutable GitHub Release/source archive if repository size/security policy permits.

## OQ-004 — Hyper Turbo real throughput target

The intended design aimed to clear very large backlogs within hours and stay ahead of 4–5k new records/day. Current run retry/claimed counts and live lane drift should be measured over time to determine real imported/completed throughput and whether a different governor is needed.
