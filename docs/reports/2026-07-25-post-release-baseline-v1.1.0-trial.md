# PDP One v1.1.0-trial — Post-Release Operational Baseline

**Baseline date:** 2026-07-25  
**Repository:** `PDP-WEBBASE/PDP-One`  
**Release tag:** `v1.1.0-trial`

## 1. Purpose

This document is the authoritative post-release baseline for the first consolidated Procurement trial release. It separates GitHub source state, the Windows-installed application state, PostgreSQL business data, deployment-agent state, and backup state. These items must never be treated as identical.

## 2. GitHub release baseline

- Release tag: `v1.1.0-trial`
- Release title: `PDP One v1.1.0-trial`
- Release/main merge commit: `02f28984b68c0e8563f4bc6f789cf0aaeec1c2b6`
- Release-candidate PR: `#20`
- PR #20 status: merged
- Previous consolidated main commit: `b271e40feee3cd2f6f7b46f24bede2543a55de4e`
- Release candidate head: `653c6d5bf950e9ed3dff849ef26410e098ccae7b`
- Tag verification: `v1.1.0-trial` is identical to release merge commit `02f28984...`

## 3. Windows operational baseline

The GitHub release commit is not the same as the application commit currently installed on the Windows trial laptop.

- Accepted installed application commit: `ee5c83aeeced74f7a00ed1aaf39305e3413dfbac`
- Deployment ID: `procurement-v25-fast-load-ee5c83ae-20260725`
- Web build ID: `procurement-fast-initial-v25-20260725`
- Deployment health: `healthy`
- Browser acceptance: passed
- Full Windows shutdown/restart acceptance: passed
- Automatic startup after Windows logon: passed
- Public address: `https://pdp-one-trial.tail84ea7e.ts.net`
- Procurement workspace: `https://pdp-one-trial.tail84ea7e.ts.net/procurement`

No Windows deployment was triggered by publishing the GitHub tag and release.

## 4. Persisted data baseline

Live checks at baseline creation:

- Service: `PDP One`
- Database: `connected`
- Trial mode: `true`
- Contracts: `9`
- Receivables: `3`
- Analysis drafts: `0`

These counts are operational verification markers, not business totals guaranteed for all future dates.

## 5. Deployment agent baseline

- Agent configured: `true`
- Signed queue available: `true`
- Pending requests: `0`
- Completed responses at baseline creation: `95`
- Transport: `local signed file queue`
- Arbitrary shell execution: `false`

The agent may run only allowlisted guarded operations. It must not be treated as a general remote shell.

## 6. Backup and recovery baseline

- Verified deployment backup associated with V25: `PDP-One-final-Backup-20260725-003429`
- Restore verification for that deployment backup: passed
- Verified post-release backup tied to release commit `02f28984b68c0e8563f4bc6f789cf0aaeec1c2b6`: `PDP-One-final-Backup-20260725-075733`
- Initial isolated restore verification for the post-release backup: passed
- Independent re-verification of the post-release backup: passed
- Release stabilization deployment ID: `release-v1.1.0-trial-stabilization-20260725`
- Production changed while creating or verifying the post-release backup: no
- Expected automatic archive path for eligible verified backups: `D:\BackUp PDP-0NE-14050429-01`
- Docker volume prune is forbidden.
- PostgreSQL, private-files, Redis and Tailscale volumes must not be deleted by cleanup operations.
- Tailscale identity, MCP path token, `.env`, secrets and Windows DNS must not be changed by ordinary startup, deployment or cleanup.

The release-linked final backup is complete and independently restore-verified. Portable encrypted export is a separate interactive operation because its passphrase must be entered by the operator and must never be persisted in ChatGPT, GitHub or the deployment agent.

## 7. Active Procurement capabilities

- PostgreSQL-backed tenders, inquiries and direct-opportunity workspace
- Compact approved management UI
- Importance and urgency labels and filters
- Full, proposed and selected lists
- Search, filters, source links and dashboard summaries
- Extraction history and subsystem-management views
- Independent source controls
- First-run extraction for today plus one previous day
- Incremental normal extraction
- Explicit manual date-range re-check
- Duplicate prevention and record history
- Safe ten-second request guards
- Controlled retry only for safe GET operations
- Background refresh without returning the whole page to loading
- Polling only the active extraction run
- Fast initial load using session, dashboard summary, first notice page and first direct-opportunity page
- Lazy loading of sources, extraction history and automation settings
- Verifiable Web build marker and cache-safe HTML delivery
- Guarded analysis requests and ChatGPT analysis drafts
- Windows automatic startup, public route checking and limited Tailscale self-healing
- Guarded Preview, approval, backup, restore verification, deployment, health and rollback chain

## 8. Connector status

- Hezareh tenders: enabled/available for controlled acceptance testing
- Hezareh inquiries: enabled/available for controlled acceptance testing
- Pars Namad Data inquiries: enabled/available for controlled acceptance testing
- Pars Namad Data tenders: intentionally disabled because the public route returned inquiry content
- Setad Iran connectors: require controlled validation in the operating environment, including geographic/access limitations

Connector extraction is not considered finally accepted merely because the application is healthy. Each connector requires a controlled real-run acceptance report.

## 9. Analysis-engine status

- Versioned context, roles, prompts, keywords, company profile, qualifications and experience context are supported.
- Keywords are context for OpenAI and UI search/filtering; they are not an internal deterministic scoring engine.
- Analysis output is stored as a draft and requires human review.
- Automatic publication of decisions is disabled.
- Scheduled automatic analysis remains disabled until real-data human acceptance is completed.

## 10. Known limitations and guarded items

- This is a trial release, not the final production-complete system.
- Connector accuracy can change when source websites change.
- Pars Namad tenders remain disabled.
- Setad access can be affected by geographic and website restrictions.
- The operational Windows commit differs from the GitHub release merge commit; both identifiers must be recorded in every future deployment/release report.
- The public address depends on the Windows laptop, Rancher Desktop/Docker and Tailscale availability.
- Automatic deployment permission granted during implementation does not authorize destructive data operations, token rotation, main merges or future final releases unless separately approved.

## 11. Required next acceptance stages

1. Release-linked final backup for commit `02f28984...`: completed and independently restore-verified.
2. Create a portable encrypted, DPAPI-independent backup and verify hashes for its configured copies: requires one local operator interaction for destination and passphrase.
3. Observe startup, public access, disk growth, backups, browser session and agent health for 24–48 operational hours: scheduled.
4. Run controlled acceptance tests for each enabled connector.
5. Run human-reviewed analysis acceptance on real tenders/inquiries.
6. Implement and accept the workflow from selected opportunity through bid preparation, submission, result and contract conversion.

## 12. Change-control rule after this baseline

All new work must:

1. branch from `main` at or after release commit `02f28984...`;
2. use a separate GitHub branch and PR;
3. complete CI and Preview for the exact commit;
4. preserve database, volumes, private files, Tailscale identity and MCP token;
5. create a fresh verified final backup before Windows deployment;
6. record the GitHub source commit and installed operational commit separately;
7. complete post-deployment health and data-count checks;
8. update this baseline or its successor report after material changes.
