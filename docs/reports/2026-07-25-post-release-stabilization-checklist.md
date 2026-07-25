# PDP One v1.1.0-trial — Post-Release Stabilization Checklist

## Completed

- [x] Publish GitHub tag and release `v1.1.0-trial`
- [x] Verify tag equals release merge commit `02f28984b68c0e8563f4bc6f789cf0aaeec1c2b6`
- [x] Close obsolete PR #1 without merging it
- [x] Mark PR #1 as `completed` and `superseded`
- [x] Record authoritative post-release operational baseline
- [x] Verify live PostgreSQL connection
- [x] Verify 9 contracts and 3 receivables remain available
- [x] Verify deployment agent is configured and the signed queue is empty
- [x] Create release-linked final backup `PDP-One-final-Backup-20260725-075733`
- [x] Complete initial isolated restore verification
- [x] Complete independent restore re-verification
- [x] Schedule 24-hour operational health observation
- [x] Schedule 48-hour operational health observation

## One required local operator action

- [ ] Create the portable encrypted DPAPI-independent backup by running `CREATE-PDP-ONE-PORTABLE-BACKUP.bat`
- [ ] Select an external/off-machine destination
- [ ] Enter a new passphrase of at least 14 characters twice
- [ ] Store the passphrase separately from the backup and GitHub
- [ ] Confirm the Desktop report status is `succeeded`
- [ ] Confirm SHA-256 verified copies exist at the external destination and `D:\BackUp PDP-0NE-14050429-01`

## Observation gates

- [ ] 24-hour service/database/agent/public-access report
- [ ] 48-hour final stabilization report
- [ ] No unexplained loss of contracts or receivables
- [ ] No recurring full-screen Procurement loading regression
- [ ] No uncontrolled Docker disk growth
- [ ] Automatic startup and public access remain stable

## Next acceptance phase after stabilization

- [ ] Controlled acceptance: Hezareh tenders
- [ ] Controlled acceptance: Hezareh inquiries
- [ ] Controlled acceptance: Pars Namad inquiries
- [ ] Keep Pars Namad tenders disabled pending a verified tender route
- [ ] Controlled acceptance: Setad connectors in the operating environment
- [ ] Human-reviewed real-data analysis-engine acceptance
- [ ] Selected opportunity to bid/result/contract workflow acceptance
