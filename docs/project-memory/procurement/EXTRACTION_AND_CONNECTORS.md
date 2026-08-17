# PDP One — Extraction and Connectors

## Architecture

Connectors are modular by source and notice type. Historical accepted families include Hezareh, Pars Namad and SETAD Tender/Inquiry paths.

## Historical July acceptance snapshot

Acceptance execution `connector-acceptance-v2-final-20260725` reported:

- tested connectors: 5
- disabled: 1
- pages processed: 15
- records seen: 510
- failed records: 0
- status: succeeded with warnings

Conditions recorded:

- Pars Namad Tender connector disabled because the apparent tender route exposed Inquiry content.
- Hezareh paths had warnings around some unverified dates.
- Pars Namad Inquiry accepted with warning state.
- SETAD Tender/Inquiry accepted under public-list constraints/warnings.

This is historical evidence, not a guarantee of current external-site behavior.

## Extraction-window policy lineage

- Initial extraction: today + previous day.
- Incremental hourly/daily/normal manual run: may stop when it confidently reaches already-known records.
- Explicit date-range run: scan the full requested date window rather than stopping only because existing records appear.

## Deduplication

Avoid duplicate canonical business records while preserving:

- source occurrence
- update/version history
- cross-source evidence
- type-resolution provenance

A misleading source route name must not override actual resolved notice type.

## Live changes

Before modifying a connector:

1. `PDPONE START`;
2. read current connector code/settings;
3. read current extraction state;
4. retest live source behavior;
5. inspect concurrent connector work;
6. keep source-specific blast radius small;
7. update connector acceptance/history after change.

Do not re-enable Pars Namad Tenders solely because an old path name says Tender; live source content must first be revalidated.
