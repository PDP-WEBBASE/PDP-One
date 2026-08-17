# PDP One — System of Record Matrix

This matrix defines where each class of truth must be read from. Cached documentation helps discovery but never overrides the authoritative live source.

| Information | Authoritative source | GitHub role | Refresh rule |
|---|---|---|---|
| Source code | GitHub repository / relevant ref | authoritative | before write/deploy/merge |
| `main` identity | GitHub | authoritative | START/PRE-WRITE/PRE-DEPLOY/PRE-MERGE |
| PR/branch/CI state | GitHub | authoritative | before decisions depending on them |
| Historical decisions | Canonical Project Memory + source evidence | authoritative historical record | append/supersede |
| Active project decisions | Decision Register + latest explicit user decision | authoritative governance | every operational session |
| Historical evidence | Source Catalog / archived or manifested evidence | authoritative historical evidence | immutable |
| Current runtime health | PDP One Runtime | authoritative live state | before operational action |
| PostgreSQL business data | PDP One/PostgreSQL | authoritative live data | never infer from transfer snapshots |
| Procurement analysis run | PDP One analysis-run API | authoritative live state | before analysis changes |
| Active analysis Context | PDP One Context manifest/snapshot | authoritative live state | version/hash driven |
| Deployment queue | PDP One Deployment Agent | authoritative live state | before deployment |
| Deployment result | Exact Deployment Agent request/report | authoritative evidence | follow exact request ID |
| Deployed exact commit | Deployment report/runtime proof | authoritative | never infer from merge SHA |
| Docker/Rancher/Windows state | Windows/runtime evidence | authoritative operational state | only when relevant |
| Current ChatGPT schedules | ChatGPT Automations | authoritative live schedule state | before schedule changes |
| Desired Automation configuration | GitHub Automation Registry/specs | authoritative desired state | version controlled |
| Automation drift | Comparison: GitHub spec vs live ChatGPT Automation | derived | START + before schedule mutation |
| Backup payload | Approved backup storage | authoritative binary asset | do not copy secrets to GitHub |
| Backup metadata/history | GitHub Backup Registry + runtime reports | historical/governance | update after backup/restore event |
| Multi-chat active work | GitHub Session Issues / open PRs | authoritative coordination state | START/PRE-WRITE/PRE-DEPLOY/PRE-MERGE |
| Company résumé source | Historical PDF / approved source artifact | authoritative source evidence | preserve hash/provenance |
| Derived company capabilities | Canonical company-knowledge docs | derived knowledge | update when source changes |
| Keywords / analysis guidance | Active analysis Context + canonical policy | authoritative policy | do not replace semantic analysis with deterministic keyword scoring |

## Conflict precedence

When sources conflict, use this order unless a higher safety constraint applies:

1. Latest explicit user decision.
2. Verified live runtime for current operational facts.
3. Exact deployment evidence for deployment identity/result.
4. Current GitHub source and merged history.
5. Active ADR/Decision Register.
6. Canonical cached Current State.
7. Historical source archive / transfer package.
8. Transferred chat context.
9. Unapproved proposal.
10. Inference.

Do not hide conflicts. Record them in Current State, Gaps/Unverified, Decision Register, Incident history or Session Issue as appropriate.

## Historical snapshot rule

A historical file may be fully accurate for its timestamp and still be wrong as a current answer. Preserve it; do not silently rewrite it. Example: Transfer Package v10 states main `f2f38d...`, runtime V25 `ee5c83...`, 9 contracts and 0 analysis drafts as of July 31. Those remain valid historical evidence while the 2026-08-17 live snapshot is different.
