# PDP One — Transfer v10 Structured Registers (Record-Level Import)

Source package: `PDPOne-Transfer-Package-v10.0-2026-07-31`.

This file preserves the row-level meaning of the historical CSV registers so later chats do not depend only on condensed summaries. These values describe the **2026-07-31 historical transfer state** unless explicitly stated otherwise.

## Decision register

| ID | Title | Historical status | Evidence | Confidence | Latest valid state at transfer freeze |
|---|---|---|---|---|---|
| DEC-001 | Architecture | تأییدشده | EVD-007 | High | Docker/PostgreSQL/Nginx/Tailscale on Windows trial host |
| DEC-002 | Authentication | تصمیم نهایی | EVD-007 | High | One-step login; no 2FA; automatic logout disabled for now |
| DEC-003 | Connector modularity | تصمیم نهایی | EVD-006 | High | Separate modules for each source and notice type |
| DEC-004 | Pars Namad tenders | تصمیم نهایی | EVD-006 | High | Disable `parsnamad_tenders` |
| DEC-005 | Initial extraction | تصمیم نهایی | EVD-007 | High | Today plus one prior day |
| DEC-006 | Incremental extraction | تصمیم نهایی | EVD-007 | High | Hourly/daily/normal manual stop after confidently reaching existing records |
| DEC-007 | Range extraction | تصمیم نهایی | EVD-007 | High | Manual range continues through full requested day window even after common records |
| DEC-008 | Deduplication | تصمیم نهایی | EVD-006 | High | Do not create duplicate records; preserve updates in history and cross-source links |
| DEC-009 | AI policy | تصمیم نهایی | EVD-012 | High | Keywords are context; not deterministic scoring |
| DEC-010 | Deployment control | تصمیم نهایی | EVD-007 | High | Branch, CI, Preview, exact commit, backup, restore verify, deploy, health, rollback |
| DEC-011 | Production safety | تصمیم نهایی | EVD-005 | High | No arbitrary shell and no destructive Docker volume operations |
| DEC-012 | Operational baseline | تأییدشده | EVD-007 | High | V25 accepted Windows runtime while main/release are separate source baselines |
| DEC-013 | Current configuration management | در انتظار اجرا | EVD-003 | High | Do not begin analysis-engine acceptance until PRs 22–24 and runtime connector acceptance are reconciled |

Canonical current/superseded interpretation is maintained separately in `decisions/DECISION_REGISTER.md`.

## Deployment register

| ID | Deployment | Commit | Historical status | Backup | Note |
|---|---|---|---|---|---|
| DEP-001 | BACKLOG-001 | `cf1bcc40a0290d05fb31cce606f2521c4b9341f5` | successful | `PDP-One-final-Backup-20260720-172949` | Historical stable baseline |
| DEP-002 | V18 startup-fetch | `e8322e42ad0f9851e3a410839b7a9316d46366b1` | failed | `PDP-One-final-Backup-20260724-?` | Rejected before source/report creation |
| DEP-003 | V20 startup-fetch | `8b15854ac2015bfd10326d97bac2d70e739207b1` | successful | `PDP-One-final-Backup-20260724-210534` | Timeout/fallback and deploy diagnostics |
| DEP-004 | V21 API route | `e067d5fcc256bca66b27d0f7ec5aaa0f16dea6f3` | successful | `PDP-One-final-Backup-20260724-213524` | Nginx/API route health changes |
| DEP-005 | V22 session-poll | `27d1a6118ccec9a628b601c7ca06418c8555c7f3` | failed | `PDP-One-final-Backup-20260724-223507` | Backend image prebuild failure |
| DEP-006 | V23 build retry | `f1cd7baa798045db360c66e24cae85d4f089968e` | not installed / ambiguous | `PDP-One-final-Backup-20260724-231525` | Verifier proved old source/bundle remained |
| DEP-007 | V24 build proof | `db70cc704afaa660567c0a7be36345e1b5e9c767` | successful | `PDP-One-final-Backup-20260724-234829` | Build marker verified in browser |
| DEP-008 | V25 fast load | `ee5c83aeeced74f7a00ed1aaf39305e3413dfbac` | successful | `PDP-One-final-Backup-20260725-003429` | Accepted fast initial load and restart |

## Issues / lessons register

| ID | Issue | Cause | Latest valid state at transfer freeze | Recurrence risk |
|---|---|---|---|---|
| ISS-001 | Manual startup and changing MCP token | Early startup design | Superseded by stable startup/self-healing | Low |
| ISS-002 | False public health from Nginx-only `/healthz` | Health design | Real session/API route added to checks | Low |
| ISS-003 | Frontend returns to loading every 5 seconds | Whole-page polling | V24/V25 preserve loaded data and poll active run only | Low |
| ISS-004 | V22 backend image build failure | Network/DNS/package build instability | Retries/cache/binary preference added; V23 still not installed | Medium |
| ISS-005 | V23 healthy did not prove new bundle installed | Health/version ambiguity | Build marker and bundle verification introduced in V24 | Low |
| ISS-006 | Rancher/Docker disk growth | Build cache and WSL VHDX | Safe cleanup plus compaction; no volume prune | Medium |
| ISS-007 | Pars Namad tender route returns inquiries | Source behavior | Connector disabled | High source-change risk |
| ISS-008 | Hezareh dates partially unverified | Source parsing | Accepted with warnings; preserve raw values | Medium |
| ISS-009 | Three overlapping connector acceptance PRs | Configuration management | Unresolved at transfer freeze; canonical PR not designated | High |
| ISS-010 | Transfer ZIP cannot move live connections/runtime | Platform limitation | Reconnect and re-verify in new chat | Certain |

## Evidence register

| ID | Evidence | Source | Historical date/order | Result | Confidence |
|---|---|---|---|---|---|
| EVD-001 | Live GitHub main head | GitHub read-only search | 2026-07-31 | `f2f38d382af6bf92302d9a2169c439d4e0f94523` | High |
| EVD-002 | Release tag comparison | GitHub compare `v1.1.0-trial..main` | 2026-07-31 | tag `02f28984...`; main three documentation commits ahead | High |
| EVD-003 | Open PR inventory | GitHub open PR query | 2026-07-31 | PR22, PR23, PR24 open/draft | High |
| EVD-004 | Live PDP One system status | PDP One connector | 2026-07-31 | DB connected; 9 contracts; 3 receivables; 0 analysis drafts | High |
| EVD-005 | Deployment Agent status | PDP One connector | 2026-07-31 | configured; queue available; 0 pending; arbitrary shell disabled | High |
| EVD-006 | Connector acceptance report | PDP One connector | 2026-07-25 | 5 tested; 15 pages; 510 seen; 0 failed; warnings | High |
| EVD-007 | V25 acceptance and release chain | conversation/release notes | 2026-07-25 | V25 deployed; restart/fast-load acceptance passed | High |
| EVD-008 | V23 installation verifier | sanitized attached report | 2026-07-24 | V23 not installed; old web bundle remained | High |
| EVD-009 | V22 diagnostics | sanitized attached report | 2026-07-24 | backend image prebuild failed; production did not require rollback | High |
| EVD-010 | Portable encrypted backup | attached JSON report | 2026-07-21 | DPAPI-independent; isolated restore verified; copy hashes verified | High |
| EVD-011 | Historical restart guide | uploaded text | imported history | manual CONNECT-CHATGPT superseded by stable startup | Medium |
| EVD-012 | Transfer prompt v4 fast core | uploaded instruction file | 2026-07-31 | governing packaging requirements | High |
| EVD-013 | Previous valid transfer package | File Library build summary | 2026-07-31 | v9.0 QA PASS; secret scan PASS; ZIP test PASS; 250 entries | High |

## Backup register

| ID | Backup/path | Status | Description | Evidence |
|---|---|---|---|---|
| BKP-001 | `PDP-One-final-Backup-20260725-003429` | verified | V25 pre-deploy/final backup | EVD-007 |
| BKP-002 | `PDP-One-final-Backup-20260725-075733` | verified | post-release verified backup | EVD-013 |
| BKP-003 | `PDP-One-Portable-Backup-20260721-223550.pdpone` | verified | DPAPI-independent; isolated restore and copy hashes verified | EVD-010 |
| BKP-004 | `D:\BackUp PDP-0NE-14050429-01` | archive path | automatic verified copy destination | EVD-010 |

## Connector register

| ID | Connector | Historical status | Enabled | Pages | Seen | New | Updated | Duplicates | Failed | Note |
|---|---|---|---:|---:|---:|---:|---:|---:|---:|---|
| CON-001 | hezareh_tenders | succeeded_with_warnings | true | 2 | 40 | 0 | 40 | 0 | 0 | some records have unverified dates |
| CON-002 | hezareh_inquiries | succeeded_with_warnings | true | 2 | 40 | 0 | 40 | 0 | 0 | some unverified dates; one cross-source duplicate link |
| CON-003 | parsnamad_inquiries | succeeded_with_warnings | true | 5 | 250 | 0 | 250 | 0 | 0 | accepted with recoverable warnings |
| CON-004 | parsnamad_tenders | disabled | false | 0 | 0 | 0 | 0 | 0 | 0 | disabled because tender route exposed inquiry content |
| CON-005 | setad_tenders | succeeded_with_warnings | true | 3 | 90 | 2 | 4 | 84 | 0 | public-list-only; no CAPTCHA bypass/detail circumvention |
| CON-006 | setad_inquiries | succeeded_with_warnings | true | 3 | 90 | 28 | 62 | 0 | 0 | public-list data accepted; detail probes not performed |

## Unverified register

| ID | Historical item | Needed evidence/action | Priority |
|---|---|---|---|
| UNV-001 | Exact installed commit/deployment that produced final connector acceptance | Windows/deployment report or build marker tied to PR22/23/24 | High |
| UNV-002 | Canonical connector-acceptance PR among 22/23/24 | compare and controlled consolidation decision | High |
| UNV-003 | Current Docker/Rancher/Tailscale CLI state | request only if operational action requires it | Contextual |
| UNV-004 | Complete raw transcript of all historical chats | unavailable; chronology/evidence index used | Non-blocking |
| UNV-005 | Full source snapshots for main/release/runtime | omitted by fast-transfer policy; fetch GitHub when needed | Contextual |
| UNV-006 | 24/48-hour stability observation after V25 | no direct report in transfer sources | Future evidence |
| UNV-007 | Analysis-engine acceptance against final connector dataset | not accepted at transfer freeze | Historically high; later lineage evolved |
| UNV-008 | Direct GitHub Release API metadata | tag/source/release notes verified; full object not exported | Low |

## GitHub state register at transfer freeze

| ID | Type | Historical value/status |
|---|---|---|
| GH-001 | repository | `PDP-WEBBASE/PDP-One` verified |
| GH-002 | main | `f2f38d382af6bf92302d9a2169c439d4e0f94523` |
| GH-003 | release tag | `v1.1.0-trial` |
| GH-004 | release commit | `02f28984b68c0e8563f4bc6f789cf0aaeec1c2b6` |
| GH-PR-22 | PR22 | head `d0aeaffa46faa128d4628445818b3ad5b6f2e03c`; open/draft/mergeable |
| GH-PR-23 | PR23 | head `1948cfd5cabf0d8c1d3a104b5bd47ac93e5d67ac`; open/draft/mergeable |
| GH-PR-24 | PR24 | head `884c6eebbc207b046bcadfeab3d4442bf29bcec9`; open/draft/mergeable |

## Historical access matrix

| Resource | Access in transfer chat | Transfer behavior | New-chat action | Sensitive? |
|---|---|---|---|---|
| GitHub connector | available | does not transfer automatically | reconnect/test read access | no |
| PDP One connector/MCP | available | does not transfer automatically | reconnect; do not expose private URL | potentially |
| File Library | available | not guaranteed | upload package/required source files | no |
| Windows filesystem | reports only | does not transfer | user/agent provides reports | yes |
| Docker/Rancher/Tailscale CLI | not directly available | does not transfer | read only when operational evidence needed | yes |
| PostgreSQL live data | reachable via PDP status | does not transfer | never recreate from package | yes |
| Secrets/.env/tokens/cookies | intentionally excluded | do not transfer | reconfigure securely outside chat output | yes |

## Manifest-only / excluded assets

Transfer v10 intentionally excluded or manifested rather than embedded:

- `PDP-TENDER-SOURCE-DIAGNOSTICS-V2-20260722-003940.zip` — ~94MB raw diagnostics; retrieve only for connector forensics.
- `PDP-ONE-SETAD-CONNECTOR-CAPTURE-20260722-230502.zip` — raw SETAD capture; retrieve only for parser forensics.
- screenshots `image(69)..image(90)` — manifest-only UI evidence; retrieve for visual regression if needed.
- encrypted `.pdpone` payload — sensitive operational backup; restore outside the transfer package.

## Current interpretation rule

These registers are preserved verbatim in meaning as historical evidence. Current decisions, runtime counts, connector behavior and deployment identities must be refreshed from live sources and the canonical Decision Register rather than overwritten into this historical import.
