# PDP One — Procurement Overview

## Purpose

The procurement subsystem extracts, normalizes, deduplicates, semantically analyzes and routes Tender, Inquiry and Direct Opportunity records for human company decisions.

The company is a consulting-engineering firm; procurement analysis is intended to identify opportunities matching its qualifications, experience and strategic fields rather than simply matching words.

## Authoritative layers

1. Source/extraction evidence.
2. Normalized canonical Notice/Opportunity data in PostgreSQL.
3. AI analysis drafts and review state.
4. Human Selection/participation decisions.
5. Submission/result workflow.

## Historical external sources

Accepted architecture uses modular connector families, historically including:

- Hezareh tenders
- Hezareh inquiries
- Pars Namad inquiries
- Pars Namad tenders — disabled under DEC-004 while that route exposed inquiry content
- SETAD tenders
- SETAD inquiries

The July 25 connector-acceptance execution remains historical evidence. External websites are unstable; live source behavior must be retested before connector changes.

## Extraction policy lineage

Historical accepted rules:

- initial extraction window: today + one prior day
- normal incremental runs may stop after confidently reaching already-known records
- explicit manual date-range extraction scans the requested range rather than stopping merely because common records appear
- deduplication must preserve canonical data, source occurrences and update history

Current exact extraction settings must be read from the live system before mutation.

## Three information layers

The historical Master Design established three procurement-data levels:

- **Raw** — source-specific captured evidence.
- **Normalized** — canonical typed/dated/deduplicated records.
- **Analysis** — AI draft recommendation/review and downstream human workflow.

This separation remains a useful architectural rule.

## Recommendation vs human decision

### Recommended
An AI/ChatGPT semantic recommendation based on the active Context and current record content.

### Selected
A human/company decision to pursue the opportunity.

These states are deliberately separate.

## Current accepted list semantics

PR54 established:

- Tender and Inquiry general lists: recent operational view (implemented with a 3-day recent window at PR54).
- Recommended lists: complete effective recommendation history, not a recent-only window.
- Effective recommendation source: latest valid effective `NoticeAnalysisDraft`, not stale Notice compatibility flags.

The date-window implementation must be verified in current code before future changes.

## Selected / submitted / result

Current accepted workflow lineage:

### Tender / Inquiry
`All / Recent → AI Recommended → Human Selected → Submitted → Result`

### Direct Opportunity
`All Direct Opportunities → Selected → Submitted → Result`

Direct Opportunities intentionally do not require a separate Recommended tab under the PR57 design.

## Documents

- Selected records may use submission-document storage.
- Multi-file upload is supported in the accepted workflow.
- A file is not mandatory merely to record submission.
- Existing documents/history must be preserved; pre-submission remove actions must not erase the underlying Notice/analysis history.

## Result registration

PR57 established result registration for submitted Tender, Inquiry and Direct Opportunity records. Final Case/opportunity-result states drive display under Results.

## AI recommendation dismissal

`حذف از پیشنهادی` is a human rejection of the current effective AI recommendation:

- does not delete the Notice;
- does not delete historical AI analysis;
- creates/reuses review/audit semantics;
- removes the current effective recommendation;
- a genuinely newer future analysis may recommend the record again.

## Keyword policy

Historical keyword policy explicitly states:

`internalScoring: false`

and keywords are context for semantic analysis/UI search rather than a deterministic internal scoring engine.

High-value domains include consulting/design/studies/supervision/project-management work in:

- building/architecture/structures
- urban planning/design
- industrial estates
- special/free economic zones
- feasibility and technical-economic studies
- Article 23
- urban utilities/infrastructure
- renewable/solar energy
- GIS/surveying/spatial data
- geotechnical/structural engineering

Negative context commonly includes pure commodity/equipment purchases, routine staffing/cleaning/guarding, simple maintenance and execution-only work unless the notice also requires relevant design/study/supervision/engineering services.

Decision must be semantic and contextual, not word-presence-only.

## Safety

- AI output remains Draft.
- Human review is required.
- Analysis must not create final participation, contract, receivable or payment decisions automatically.
- Do not cancel an active long-running run for unrelated UI work.
