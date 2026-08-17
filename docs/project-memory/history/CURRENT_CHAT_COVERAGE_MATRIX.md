# PDP One — Current Chat Coverage Matrix

This matrix proves that the implementation wave carried in the current chat was not reduced to a single summary.

| Topic | Captured | Canonical destination | Independent evidence / status |
|---|---|---|---|
| Recommendation display mismatch | Yes | Timeline, DEC-016, Procurement Overview | PR54 live GitHub metadata |
| Tender recommendations | Yes | Procurement Overview/Workflow | PR54 |
| Inquiry recommendations | Yes | Procurement Overview/Workflow | PR54 |
| stale `ProcurementNotice.is_recommended` | Yes | DEC-016 | PR54 root-cause body |
| latest effective `NoticeAnalysisDraft` source | Yes | DEC-016 / Procurement Overview | PR54 |
| general recent vs full recommended list | Yes | DEC-016 / Procurement Overview | PR54 |
| PR54 exact head/merge/gates | Yes | Timeline | head `5b0e734a...`; merge `833dc8e3...` |
| management toolbar | Yes | Timeline / DEC-020 | PR55 |
| selected Tender/Inquiry actions | Yes | DEC-018/019 / Workflow | PR55 |
| safe remove-selected semantics | Yes | DEC-018 | PR55 |
| submission documents | Yes | DEC-019 / Workflow | PR55/57 |
| PR55 exact head/deploy/merge | Yes | Timeline | head `20371462...`; deployment `procurement-ui-v23...`; merge `cd306a35...` |
| management top-level tab | Yes | Timeline | PR56 |
| analysis controls placement | Yes | Timeline | PR56 |
| archive Timeout | Yes | DEC-020 / Timeline | PR56 root cause |
| full archive pagination anti-pattern | Yes | Architecture/Workflow | PR56 |
| bounded Case + Notice-detail lookup | Yes | DEC-020 | PR56 |
| Direct Opportunity selection | Yes | DEC-021 / Workflow | PR56 |
| Direct selected documents/send | Yes | DEC-021 / Workflow | PR56 |
| PR56 exact deploy/health/merge | Yes | Timeline | `1837bdc7...`; requests `cb08e7ff...`, `e3b7bceb...`; merge `7ab4db69...` |
| result registration | Yes | DEC-022 / Workflow | PR57 |
| Submitted → Results | Yes | DEC-022 / Workflow | PR57 |
| zero-file submission | Yes | DEC-019 / Workflow | PR57 |
| Direct Recommended tab removal | Yes | DEC-021 | PR57 |
| human reject AI recommendation | Yes | DEC-023 | PR57 |
| Notice/history preservation on AI dismiss | Yes | DEC-023 | PR57 |
| PR57 deployment/health/merge | Yes | Timeline | exact `9e1a48c5...`; deploy request `ffe85f05...`; health `7b924f98...`; merge `f531471d...` |
| analysis schedule/batch investigation | Yes | Analysis Engine / Timeline | current-chat investigation |
| persistent active run | Yes | Analysis Engine / Current State | live run `755ad573...` |
| `include_previously_analyzed=true` interpretation | Yes | Analysis Engine / Current State | live run read |
| `include_expired=true` | Yes | Analysis Engine / Current State | live run read |
| frozen run snapshot problem | Yes | DEC-024 / Analysis Engine | PR58 + live proof |
| adaptive admission | Yes | DEC-024 / Analysis Engine | PR58/live run metadata |
| `newest_first` | Yes | DEC-025 / Analysis Engine | PR58/live run metadata |
| atomic multi-lane claims | Yes | DEC-026 / Analysis Engine | PR58 |
| 21,311 fresh items admitted proof | Yes | Timeline / Analysis Engine | PR58 body |
| historical 43,944 / 6,670 / 37,261 snapshot | Yes | Timeline / Analysis Engine | PR58 body |
| PR58 first failed deploy record | Yes | Timeline | PR58 body; retained as failure |
| controlled successful exact redeploy | Yes | Timeline/Current State | request `49dc7f7e...` verified live |
| PR58 merge | Yes | Timeline | `b99dfedc...` |
| Hyper Turbo desired thresholds | Yes | DEC-027 / Automation Registry | current-chat automation creation |
| Lane 1 rule | Yes | Automation Registry/Runtime Context | live task read |
| Lanes 2–8 threshold semantics | Yes | Automation Registry | live task read |
| AI Draft/human review/no financial side effects | Yes | Guardrails / Analysis Engine / Automation Registry | live prompts + PR58 |
| live Automation drift | Yes | Current State / Automation Registry / Gap-101 | live Automations: lane 3/5 disabled |
| project-memory design discussion | Yes | DEC-029..036 / START-HERE | user-approved prompt |
| federated GitHub/Server/Automation authority | Yes | DEC-030 / System of Record | user decision |
| full Transfer-v10 semantic ingestion | Yes | DEC-031 / Source Catalog/Coverage | user decision + 69/69 audit |
| `PDPONE START` activation keyword | Yes | DEC-032 / START-HERE | latest explicit user decision |
| multi-chat simultaneous coordination | Yes | DEC-034 / Multi-Chat Coordination | user decision |
| live-source rather than stale file copies | Yes | DEC-030 / Live Source Registry | user decision |
| schedule governance / self-bootstrap context | Yes | DEC-035 / Automation Registry | user decision |

## Current bootstrap session

- Activation: `PDPONE START`
- Session: `PDP-SESSION-20260817-PROJECT-MEMORY-BOOTSTRAP`
- GitHub Issue: #59
- Branch: `docs/project-memory-bootstrap-20260817`
- Runtime/DB/Automation mutation during bootstrap: **none**

## Rule

Any future significant event in this chat before bootstrap closure must be appended to the Session Log/Timeline before the session is considered complete.
