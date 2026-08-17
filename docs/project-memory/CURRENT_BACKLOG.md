# PDP One — Current Backlog

This file contains **active or intentionally unresolved** work only. Historical completed items belong in the Timeline/Session/Deployment/Incident records.

Last bootstrap review: 2026-08-17.

| ID | Priority | Status | Work item | Dependency / evidence | Next action |
|---|---|---|---|---|---|
| BL-001 | High | Open / drift | Reconcile live Hyper Turbo Automation state: lanes 3 and 5 are disabled although the PR58 desired >=20k policy described eight lanes. | Live Automations + DEC-027/DEC-035 | In a separately activated schedule-change session, determine whether this drift is intentional; do not auto-enable during memory bootstrap. |
| BL-002 | Medium | Open / stale | Reconcile old open PR45 and PR46 with current `main`. | GitHub PR45/46, newer accepted startup/deployment lineage | Review whether they are fully superseded, partially valuable or should be closed/reimplemented. Do not merge old heads directly. |
| BL-003 | High | In progress | Complete canonical Project Memory bootstrap and QA. | Issue #59 / branch `docs/project-memory-bootstrap-20260817` | Finish source/company/procurement/automation/infra registries, governance templates, CI memory check, PR and merge. |
| BL-004 | High | Running operational workload | Clear procurement analysis backlog while preserving newest-first priority. | Active run `755ad573...`; live run status | Continue through governed ChatGPT Automations; do not cancel/restart for unrelated UI work. Track actual throughput and drift. |
| BL-005 | Medium | Observation needed | Measure actual Hyper Turbo throughput versus designed capacity and large retry/claimed counters. | Live run counters and Automation run history | Add performance snapshots/alerts without changing AI decision semantics. |
| BL-006 | Medium | Open architecture follow-up | Make Automation Runtime Context/spec versioning consumable by future scheduled tasks. | DEC-035 | After memory bootstrap, modify tasks only in a separate `PDPONE START` automation session; current bootstrap records specs but does not mutate live tasks. |
| BL-007 | Medium | Open evidence improvement | Expand company résumé page-level index and source-linked capability register as new/updated résumé evidence arrives. | Resume SHA `2a8fe5...` | Preserve page provenance; never infer qualifications not present in source. |
| BL-008 | Low/Medium | Historical evidence gap | Locate full raw historical chat transcripts or additional continuation packages if independently available. | Transfer v10 UNV-004 | Manifest when available; never reconstruct absent chat lines from summaries. |

## Completed / removed from active backlog during canonicalization

- Historical July connector-acceptance PR22–24 reconciliation is no longer the current project blocker; preserve it in history rather than treating it as today's next action.
- PR54–PR58 implementation work is completed/merged and therefore belongs in Timeline/Decision/Session history.
- Cold Windows reboot acceptance and earlier recovery items are historical accepted evidence unless a new incident reopens them.

## Rule

Every activated session must re-read this file and update it when it creates, completes, supersedes or materially changes a backlog item.
