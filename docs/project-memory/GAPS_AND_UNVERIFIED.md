# PDP One — Gaps and Unverified Items

Do not fill these gaps by inference. A historical source can be incomplete without being wrong.

## Historical Transfer v10 gaps

### GAP-001 — Full raw historical chats unavailable
- Transfer v10 explicitly states that the imported historical conversation context was summarized rather than reconstructed line-by-line.
- Impact: Canonical history can fully ingest the available Decision Log, chronology, evidence, implementation history and other artifacts, but it cannot claim verbatim completeness of omitted conversations.
- Resolution: register a raw transcript later only if an authentic source becomes available.

### GAP-002 — July exact deployed connector-acceptance commit
- At the July 31 transfer freeze, the exact Windows commit containing final connector acceptance was not recorded in the transfer state.
- Later project context continued beyond this gate, but the historical uncertainty must remain visible.

### GAP-003 — Canonical July PR22/23/24 identity at transfer freeze
- Transfer v10 recorded three overlapping open connector-acceptance PRs and could not determine the canonical one purely from exported metadata.
- Later history indicates connector-acceptance lineage was eventually accepted; the July snapshot remains historically unresolved.

### GAP-004 — Transfer-package live runtime commands
- Transfer v10 could not include direct Windows/Docker/Rancher/Tailscale CLI state or private live MCP connectivity.
- Current state must always be re-read from live sources, not inferred from the package.

### GAP-005 — Large external evidence omitted by package design
- Full raw connector diagnostic archives, screenshots, encrypted portable backup payload and complete repository snapshots were manifest-only/excluded.
- Their logical existence and retrieval purpose are preserved in Source/Asset registries.

### GAP-006 — July 24h/48h post-V25 observation
- The transfer package did not contain completed 24h/48h observation evidence at freeze time.
- Later stability/reboot evidence belongs to post-transfer history and must not rewrite the July gap.

### GAP-007 — Direct release-API metadata
- Transfer v10 recorded a release baseline but did not include a full direct release API export.

## Current bootstrap gaps / drifts

### GAP-101 — Hyper Turbo Automation Drift
- Historical desired PR58 policy described eight enabled lanes above 20k backlog.
- Live 2026-08-17 observation: lanes 1,2,4,6,7,8 enabled; lanes 3 and 5 disabled.
- Status: **UNRESOLVED / NON-BLOCKING FOR DOCUMENTATION BOOTSTRAP**.
- Do not automatically enable disabled lanes in this session.

### GAP-102 — Old open PR45 and PR46
- Both remain open against older bases.
- Their content may have historical value, but their current applicability has not been intentionally reconciled against modern `main`.
- Status: **UNRESOLVED / STALE WORK**.

### GAP-103 — Raw source binaries are not all copied into this bootstrap branch
- The complete Transfer v10 package was verified locally by SHA and file-level checksums and its 69 sources are fully inventoried/semantically ingested.
- The 10.8MB résumé PDF is manifested by exact SHA and used to derive company knowledge, rather than embedded as a new binary commit in this documentation bootstrap.
- Original package/source availability is therefore a source-location concern separate from canonical knowledge coverage.
- Future archival storage may add the immutable binary package/release asset after a separate repository-size/storage-policy decision.

### GAP-104 — Page-level résumé indexing depth
- The résumé is 66 pages and full text was extracted; representative pages were visually validated.
- Canonical company knowledge will cite section/page ranges conservatively. If future decisions require exact evidence from a specific certificate/project page, re-open the source page before treating details as current proof.

### GAP-105 — Live connector behavior after July acceptance
- Current `get_system_status` still exposes the old July connector-acceptance object.
- It is historical acceptance evidence, not proof that external websites currently behave identically.
- Any connector change must re-test the live source.

## Resolution rule

When a gap is resolved, keep the original entry and append:

- resolution date
- evidence
- session/PR
- new verified state

Do not delete the historical uncertainty.
