# PDP One — Live Source Registry

The registry answers: **for current truth about X, where must a session read?**

Historical files and cached current-state documents help discovery but do not replace these authoritative sources.

| Source ID | Subject | Authority | Access | Refresh | Snapshot policy |
|---|---|---|---|---|---|
| LIVE-GH-REPO | repository/default branch/settings | GitHub | GitHub connector | START / before governance change | record refs/events, not full repo copies |
| LIVE-GH-MAIN | current `main` commit | GitHub | commits/repo read | START, PRE-WRITE, PRE-DEPLOY, PRE-MERGE | historical commit refs retained |
| LIVE-GH-PRS | open/merged PR state | GitHub | PR search/info | START + conflict checkpoints | PR metadata/history retained |
| LIVE-GH-ISSUES | active PDP work/session issues | GitHub | issue search/read | all context checkpoints | final session log promoted to repo |
| LIVE-GH-CI | current workflow/run result | GitHub Actions | GitHub connector | before deploy/merge | important run IDs recorded |
| LIVE-PDP-SYSTEM | application/DB/business summary | PDP One Runtime | `get_system_status` | START when runtime relevant; PRE-DEPLOY/PRE-MERGE | timestamped safe counts may be retained |
| LIVE-PDP-DEPLOY-AGENT | deployment queue/disk/shell policy | PDP One Runtime | `get_deployment_status` | before deployment | record request/report evidence |
| LIVE-PDP-DEPLOY-REPORT | one exact deploy result | Deployment Agent | `get_deployment_report(request_id)` | poll exact accepted request | immutable evidence by request ID |
| LIVE-PDP-HEALTH | post-deployment health | PDP One Runtime | `check_deployment_health` | after deploy | record request/result |
| LIVE-PDP-ANALYSIS-RUN | active persistent analysis run/counters | PDP One Runtime | `get_procurement_analysis_run_status` | analysis session START and before run changes | retain timestamped metrics, never overwrite history |
| LIVE-PDP-CONTEXT | active analysis Context | PDP One Runtime | context manifest/snapshot tools | refresh when version/hash changes | version/hash retained |
| LIVE-PDP-CONNECTORS | extraction/connector settings and results | PDP One Runtime | connector/extraction read tools | before connector/extraction changes | acceptance snapshots retained historically |
| LIVE-PDP-DB | procurement/contracts/receivables source data | PostgreSQL through PDP One | domain read tools | whenever live records are required | do not mirror raw DB into GitHub |
| LIVE-WIN-RUNTIME | Docker/Rancher/Windows/Tailscale state | Windows host/runtime reports | PDP Agent/approved reports | only when operationally relevant | diagnostics may be archived sanitized |
| LIVE-CHATGPT-AUTO | actual scheduled tasks | ChatGPT Automations | Automations service | START for schedule work; before/after mutation | desired spec + important live snapshots |
| LIVE-GH-AUTO-SPEC | desired automation policy | GitHub project memory | automation registry/spec files | every automation session | version-controlled |
| LIVE-BACKUP-ASSET | actual backup payloads | approved backup locations | local/portable backup workflow | restore/retention actions | do not put secret-bearing payload in docs |
| LIVE-PROJECT-MEMORY | active governance/decisions | GitHub project memory | repository | every activated session | append/supersede, not erase |

## Source type model

### Historical immutable source
Evidence tied to a time/version. Example: `PDPOne-Transfer-Package-v10.0-2026-07-31`.

### GitHub live source
Read the latest relevant repository ref; do not use an old copied source file as current truth.

### Server live source
GitHub stores locator, safety and snapshot provenance; current values are fetched from PDP One/Windows.

### ChatGPT Automation live source
GitHub stores logical desired spec. The actual Task's enabled state/schedule/prompt is verified from ChatGPT Automations.

## Current live observations captured during bootstrap

### GitHub
- main: `b99dfedc43c64c00b536bcb625d62499d7f1a4c3`
- open PRs: #45, #46
- no pre-existing `pdp-active-work` Issue found before bootstrap

### PDP One
- database connected
- deployment queue available; no pending request at observation
- exact deployed commit proven by request `49dc7f7e...`: `d2d70c67f5e1e3290a6a165b953118e4e7f90c9f`
- active analysis run: `755ad573...`
- `newest_first` and adaptive admission active

### Automations
Observed six enabled Hyper Turbo lanes: 1,2,4,6,7,8. Lanes 3 and 5 are disabled. This differs from the historical desired eight-lane >=20k design and is recorded as Automation Drift.

## Freshness rules

- Current numbers in `CURRENT_STATE` expire as operational truth after the session; refresh before decisions.
- A deployment identity remains evidence for that deploy but does not prove a later deploy did not occur; check deployment history/live state when relevant.
- An Automation prompt/schedule must be re-read before modification.
- Connector source behavior is externally unstable. July acceptance reports are evidence, not a guarantee of August behavior.
- Company résumé and historical policy documents are stable sources until an explicitly newer source is registered.

## Failure to refresh

If a required live source cannot be read, mark the current fact `UNVERIFIED`. Do not silently use an old snapshot. For a write that depends on that current fact, stop or restrict the operation according to risk and record `context_sync_failed`/gap as appropriate.
