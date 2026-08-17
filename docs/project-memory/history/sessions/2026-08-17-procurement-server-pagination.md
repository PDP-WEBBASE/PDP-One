# PDP Session — Procurement server pagination and lazy loading

- Session ID: `PDP-SESSION-20260817-PROCUREMENT-SERVER-PAGINATION`
- Active-work Issue: #79
- PR: #82
- User decision: approved implementation of real server-side pagination, lazy loading by tab, newest-first notice ordering, and narrowly-scoped query/index optimization where page-sized endpoints remain slow.
- Integration dependency: PR #78 / Session #77; implementation branch was based on the accepted PR78 application lineage to preserve the extraction-schedule editor changes. Deployment and merge are sequenced after PR78 completes.

## Scope

- Default list page size: 50.
- User-selectable page sizes: 30 / 50 / 100, hard server cap 100.
- Numeric page navigation with previous/next, current page, total pages and total records.
- Server-side filtering before pagination for procurement workflow views.
- Notice lists ordered by newest valid `published_date`, with deterministic `last_seen_at` / ID tie-breaking.
- Direct opportunities ordered by newest activity.
- Remove the historical full recommended-list background prefetch loop.
- Preserve latest valid `NoticeAnalysisDraft` as the recommendation source of truth.
- Add only the non-destructive index needed for latest-draft lookup.

## Safety / non-goals

- No timeout inflation as a substitute for performance work.
- No change to AI recommendation semantics or human-selection semantics.
- No cancellation/restart of the active procurement analysis run.
- No destructive database, Docker, Rancher or volume operation.
- No local application image build.

## Implementation checkpoint

Branch: `feat/procurement-server-pagination-20260817`.

Implemented at the first PR checkpoint:
- bounded DRF page-size pagination;
- server-side recent/workflow/source/urgency filtering;
- recommended-query latest-draft ranking optimization;
- latest-analysis draft composite index migration;
- server-side workflow filtering for direct opportunities;
- web pagination/lazy-loading layer with 30/50/100 controls;
- removal of the V22 up-to-100-page recommended prefetch behavior;
- focused backend/frontend regression tests.

Runtime deployment evidence, measured endpoint timing, final exact commit, merge identity and completion state will be appended only after the development-fast acceptance sequence completes.
