# Procurement and Opportunities Phase 1 — Baseline

- Status: implementation started on an isolated branch
- Branch: `feature/procurement-opportunities-phase-1`
- Base branch: `main`
- Base commit: `44a67c405a0ba7352bfcab8ec8ae6b87aa1b4351`
- Base release: `v1.0.3-trial`
- Scope approved by the user: tenders, inquiries, management dashboard, direct/off-system opportunities, source management, extraction scheduling, AI analysis, retention, and narrowly scoped MCP tools

## Verified repository baseline

- Backend: Django and Django REST Framework under `backend/`
- Database: PostgreSQL is the business source of truth
- Queue: Celery and Redis are configured
- Frontend: Persian RTL responsive web/PWA under `app/`
- ChatGPT boundary: REST API through narrowly scoped MCP tools under `services/pdp_mcp/`
- Existing domain models: Contract, AnalysisReport, Receivable, PaymentReceipt, AuditEvent
- Existing API base: `/api/v1/`

## Approved initial sources

Enabled for Phase 1 implementation:

- `hezareh_tenders`
- `hezareh_inquiries`
- `parsnamad_tenders`
- `parsnamad_inquiries`

Defined but disabled pending daytime technical reconnaissance:

- `setad_tenders`
- `setad_inquiries`

Each site and each tender/inquiry connector must be independently enabled or disabled. Disabling a source must not delete previously collected data.

## UX constraints

- Do not ask users to re-enter extracted information.
- Keep routine forms short and progressively disclose advanced fields.
- A direct/off-system opportunity must be registrable with title, employer, and next action.
- Common actions must be available from list views.
- Optional information must not block workflow progression.

## Safety and deployment gates

This branch must not be deployed directly. Required flow:

`Branch → tests/security review → Preview → explicit user approval → fresh verified backup → deploy exact approved commit → health/data/volume checks → rollback on failure`

The work must not rotate MCP tokens, change Tailscale identity, delete Docker volumes, restore a backup, modify operational data outside migrations, or merge into `main` without the later explicit gates.

## Backup reference

The latest user-provided successful portable-backup report before implementation recorded:

- Status: succeeded
- File: `PDP-One-Portable-Backup-20260721-223550.pdpone`
- SHA-256: `23fc346d5d97c48fbc48eaabad015b407db9a87000f5177df40078afc95f2cf6`
- Isolated restore verification: passed
- DPAPI independent: true
- Verified copies: external drive and `D:\BackUp PDP-0NE-14050429-01`

This is historical evidence from the system-generated report, not a new runtime inspection. A fresh final backup is still mandatory immediately before any approved deployment.

## Runtime limitation

This baseline records repository and previously verified report state. No direct Windows runtime, Docker volume, database, or local filesystem mutation was performed while creating this document.
