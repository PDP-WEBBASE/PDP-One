# PDP One — Domain and Business Rules

## Company / opportunity fit

PDP is a consulting-engineering organization. Opportunity analysis should prioritize consulting, studies, design, supervision, project/plan management and closely related engineering services that match current qualifications and documented experience.

Historical/high-value capability families include building/architecture, urban planning/design, industrial estates, special/free zones, feasibility/technical-economic studies, Article 23, utilities, renewable/solar energy, GIS/surveying/spatial data, structures/geotechnics and MEP where current qualifications support the requirement.

## Semantic analysis

- Keywords are context/search guidance, not deterministic internal scoring.
- Pure commodity/equipment purchases, routine staffing/cleaning/guarding, simple maintenance and execution-only work are normally low fit unless relevant design/study/supervision/engineering scope is present.
- Ambiguous high-value employers/titles may require deeper analysis rather than deterministic rejection.
- Every claimed item receives an analysis result; uncertainty is represented as confidence/needs-information/risk, not by silently dropping the item.

## Recommendation and review

- AI output is Draft.
- AI `Recommended` is not human `Selected`.
- Human review remains required.
- Dismissing a recommendation does not delete the Notice or analysis history.
- A newer valid AI analysis may change the effective recommendation later.

## Procurement records

- Deduplicate business records while preserving source/update history.
- Tender and Inquiry type resolution must not be inferred solely from a misleading source route.
- Disabled source/type connectors remain disabled until deliberately revalidated and re-enabled.

## Workflow

Tender/Inquiry lineage:

`All/Recent → Recommended → Selected → Submitted → Result`

Direct Opportunity lineage:

`All Direct → Selected → Submitted → Result`

- Selected removal is safe workflow cleanup, not source-record deletion.
- Submission may be recorded with zero files.
- Existing attached files/history must be preserved.
- Result registration uses domain-valid final outcome state.

## Analysis backlog

- Fresh notices take priority over old backlog (`newest_first`).
- New eligible notices can be adaptively admitted to the active persistent run.
- Claims use lease/token integrity and must not be duplicated intentionally across lanes.
- Do not cancel a healthy active run for an unrelated UI/configuration task.

## Contracts / finance

AI-created contract, receivable, payment or financial actions remain Draft unless an explicitly approved workflow says otherwise. Never represent a Draft as approved/final.

## History and audit

- Important decisions/actions should be attributable to user/AI/system/session where applicable.
- UI disappearance does not imply database deletion.
- Append history and mark supersession instead of rewriting the past.

## Access / authentication historical decision

The accepted project decision recorded one-step login, no 2FA and disabled automatic logout for the current phase. Treat this as active project policy unless a later explicit security decision supersedes it; do not infer broader security posture from it.
