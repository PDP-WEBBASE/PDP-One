# PDP One — Source Catalog

## Transfer Package v10

- Source ID: `SRC-TRANSFER-V10`
- Name: `PDPOne-Transfer-Package-v10.0-2026-07-31`
- Type: Immutable Historical Source Package
- ZIP SHA-256: `fac51cd0ee4999b53fcae613c0ca6186a7e3fdcb4e7f99f1c0e606b71a62fff4`
- Files: 69
- Extracted bytes: 11,318,119
- Internal checksum inventory: 68 covered files; 68 PASS
- Historical date/freeze: 2026-07-31
- Current-state authority: **No**. It is evidence for the freeze date.
- Full per-file inventory/SHA/status: `TRANSFER_V10_COVERAGE_MATRIX.csv`.

### Preservation model

All 69 files are inventoried and their identifiable historical knowledge is mapped into canonical memory. The original verified transfer package remains the immutable source evidence. The large 66-page résumé PDF is represented by exact SHA and derived company knowledge/page index; its binary is not duplicated into this documentation branch. Missing full raw historical chat transcripts are explicitly recorded as a Gap rather than reconstructed.

## Primary historical knowledge groups

### Project state and executive history
- `00-PDPOne-Transfer-Package-README.md`
- `01-PDPOne-Executive-Summary.md`
- `05-PDPOne-Current-Technical-State.md`
- `14-PDPOne-Complete-Project-Dossier.md`
- `project-state.json`
- `transfer-manifest.json`

Derived into: Current-vs-historical state rules, Architecture, Timeline, Source/System-of-Record model.

### Decisions / chronology / supersession
- `03-PDPOne-Decision-Log.md`
- `15-PDPOne-Conversation-Chronology.md`
- `20-PDPOne-Conversation-Evidence-Index.md`
- `42-PDPOne-Contradiction-And-Supersession-Register.md`
- `decision-register.csv`
- `evidence-register.csv`

Derived into: `decisions/DECISION_REGISTER.md`, `history/TIMELINE.md`, Gaps and governance rules.

### Implementation / incidents / roadmap
- `04-PDPOne-Implementation-History.md`
- `09-PDPOne-Issues-And-Lessons.md`
- `10-PDPOne-Backlog-And-Roadmap.md`
- `22-PDPOne-Immediate-Next-Actions.md`
- `issues-register.csv`

Derived into: Timeline, Current Backlog, safety/recovery lessons.

### Deployment / release / runtime evidence
- `38-PDPOne-Deployment-Gates-And-Release-History.md`
- `44-PDPOne-Release-v1.1.0-trial-Baseline.md`
- `45-PDPOne-V25-Operational-Baseline.md`
- `deployment-register.csv`
- `deployment/*`
- `release/*`
- `diagnostics/*`

Derived into: Architecture, Backup/Recovery, Timeline, deployment decisions and current exact-identity rules.

### Connectors / procurement
- `33-PDPOne-Procurement-Current-State.md`
- `35-PDPOne-Connector-Registry-And-Test-Matrix.md`
- `connector-register.csv`
- `evidence/connector-acceptance-summary.json`
- `attachments/11_KEYWORD_POLICY_AND_LISTS.md`

Derived into: Procurement Overview, Analysis Engine, Recommendation policy, connector/live-source rules.

### Access / assets / environment
- `06-PDPOne-Asset-Inventory.md`
- `access-matrix.csv`
- `assets-manifest.csv`
- `github-state.csv`
- `github/*`
- `control/*`

Derived into: Resource Registry, Live Source Registry, System of Record Matrix.

### Backup / recovery
- `17-PDPOne-Backup-And-Restore.md`
- `11-PDPOne-Recovery-And-Restart-Guide.md`
- `backup-register.csv`
- `backup-and-restore/*`
- historical restart/hotfix attachments

Derived into: `infrastructure/BACKUP_AND_RECOVERY.md`, Timeline and Guardrails.

### Historical design intent
- `attachments/PDPOne-Master-Design-And-Implementation-Prompt.txt`
- `attachments/PDPOne-Transfer-Prompt-Fast-Original-Core-v4.0.txt`
- `13-PDPOne-New-Chat-Master-Prompt.md`

Derived into: architecture/domain roadmap and governance history. Historical rules that conflict with later decisions are marked Superseded, not silently treated as current.

### Company evidence
- `attachments/PDP-G-14-company-resume.pdf`
- SHA-256: `2a8fe53332602c8f1dbf36abfb1abf2e5de79a7a91ed48b6722ec3b9ee527c93`
- 66 pages

Derived into: `company-knowledge/COMPANY_PROFILE.md` and source/page index.

## External / manifest-only historical evidence

Transfer v10 recorded assets intentionally not embedded in the ZIP, including large raw connector diagnostic captures, historical screenshots, encrypted `.pdpone` payload, full raw chat transcript and full repository snapshots. These are not reconstructed. Their absence is recorded in `GAPS_AND_UNVERIFIED.md` and their logical purpose remains historical evidence.

## Post-transfer sources

### GitHub PR54–PR58
Live GitHub PR metadata was re-read during bootstrap. These PRs provide independent source evidence for the current-chat implementation wave and exact head/merge identities.

### PDP One Runtime
Live bootstrap evidence from:
- system status
- deployment status
- analysis-run status
- exact deployment report `49dc7f7e...`

These are current-source observations, not archived July snapshots.

### ChatGPT Automations
Live Automation state was read during bootstrap and exposed a six-enabled-lane state with lanes 3 and 5 disabled. This is the authoritative live schedule observation at the timestamp; desired eight-lane history remains separately preserved.

## Provenance rule

Every canonical fact should be traceable to one or more of:

- Transfer v10 source path/SHA
- GitHub PR/commit/issue
- exact Deployment Agent request/report
- PDP One live API/tool observation
- ChatGPT Automation observation
- explicit user decision in a governed session

If no reliable source exists, record a Gap rather than fabricate provenance.
