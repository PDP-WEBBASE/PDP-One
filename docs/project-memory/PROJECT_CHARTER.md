# PDP One — Project Charter

## Project

**PDP One** is the internal integrated management platform for Mehandsin Moshaver Tarh-o-Barnameh Pars (PDP), with an initial and mature focus on procurement/tender intelligence and an enterprise roadmap covering contracts, projects, finance, documents, HR, quality, risk and company knowledge.

## Mission

Provide one controlled, auditable operational system in which PDP can:

- collect and normalize opportunity data;
- avoid duplicate/fragmented records;
- use ChatGPT/OpenAI for semantic analysis and decision support;
- preserve human authority over business decisions;
- connect opportunities to submission/result/contract/project/financial workflows over time;
- maintain a searchable company résumé/qualification knowledge base;
- operate safely on a Windows/Docker/PostgreSQL runtime;
- evolve through GitHub-governed, exact-version change management;
- preserve the complete project history so development can continue across multiple ChatGPT conversations without contradiction.

## Historical design domains

The Master Design source enumerated a broad target scope:

1. tenders/inquiries/opportunities;
2. business development / CRM;
3. qualifications and company capacity;
4. contracts and agreements;
5. technical/project management;
6. finance and receivables;
7. accounting or accounting integration;
8. human resources;
9. documents/correspondence;
10. quality;
11. risk/claims/change management;
12. company knowledge/résumé;
13. management dashboards/KPIs;
14. alerts/deadlines;
15. settings/access/Audit Log.

These domains are **design intent**, not proof that every subsystem is fully implemented. Current implementation status must be read from live code/runtime.

## Current primary operating domain

The most developed documented domain is procurement intelligence and its downstream human workflow:

- source extraction
- normalization/deduplication
- AI analysis/recommendation
- human selection
- documents/submission
- results
- Direct Opportunities
- operational analysis backlog/automation

## Core business principles

- AI advises; humans decide.
- Recommended and Selected are separate states.
- Business history is preserved rather than deleted for UI convenience.
- A source Notice and its AI analysis are not erased merely because a user dismisses a recommendation or removes an eligible pre-submission Case.
- Data provenance and exact-version identity matter.
- Duplicate source publications should converge into canonical business records with source/history evidence.

## Technical principles

- PostgreSQL is the primary structured-data system of record.
- Files remain file assets with metadata references, not arbitrary blobs forced into project memory.
- GitHub controls source/history/desired state, not live database replication.
- Dynamic current facts are refreshed from the responsible live source.
- Application deployments use immutable exact images/commits.
- No arbitrary shell and no destructive volume shortcuts.

## AI/analysis principles

- Semantic analysis uses current company Context/qualifications/experience.
- Keywords assist Context/search and do not become deterministic internal scoring.
- Analysis outputs are AI Drafts requiring human review.
- New opportunities should not be delayed by large historical backlog; active policy uses newest-first claims/adaptive admission.

## Change-governance principle

No PDP One mutation occurs from a general conversation. The operational session must begin with:

`PDPONE START`

Then Context Sync and multi-chat conflict checks are mandatory.

GitHub Project Memory is the long-term shared context across chats.
