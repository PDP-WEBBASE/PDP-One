# PDP One — Procurement Workflow

## Authority model

The workflow intentionally separates AI advice from company decisions.

- **AI Recommended**: machine analysis draft.
- **Human Selected**: company/user decision to follow the opportunity.
- **Submitted**: participation/proposal has been recorded as sent.
- **Result**: outcome after submission.

## Tender and Inquiry

Canonical accepted lineage:

`All / Recent → Recommended → Selected → Submitted → Results`

### All / Recent
Operational list of extracted/normalized notices. PR54 implemented a recent 3-day view for the general Tender/Inquiry lists. Verify current code before changing the window.

### Recommended
Complete effective AI recommendation history. The latest effective valid analysis draft is authoritative; stale compatibility flag `ProcurementNotice.is_recommended` is not.

Human actions include:

- `انتخاب` — creates/moves into the human-selected workflow.
- `حذف از پیشنهادی` — rejects current AI recommendation without deleting the Notice/history.

### Selected
Human-selected Case state. Accepted actions include:

- remove from selected, subject to history-safety constraints;
- manage submission documents;
- record submission.

Safe removal deletes only an eligible pre-submission Case; it does not delete the source Notice or AI analysis. If submission/history documents make deletion unsafe, preserve history rather than deleting.

### Submitted
A Case can become Submitted with or without an attached file under PR57.

If files are selected, use the established submission-document path. Do not invent empty placeholder files merely to satisfy a UI requirement.

### Results
Submitted Cases support explicit result registration. Historical PR57 result states included won/lost/cancelled/renewed for Tender/Inquiry result UI; current backend enum should be verified before future expansion.

## Direct Opportunities

Canonical accepted lineage after PR57:

`All Direct Opportunities → Selected → Submitted → Results`

The old Direct `Recommended` tab is intentionally absent.

### Selection
Direct records are selected from the full Direct list and use the shared selected-action architecture.

### Remove from selected
Preserve the underlying Direct Opportunity and history; reset/move workflow only according to the implemented safe semantics.

### Documents / send
Direct Opportunities share `submission-documents` infrastructure rather than a separate file store.

Submission with zero files is allowed.

### Results
Direct result recording uses the established opportunity-results backend and updates the workflow state. Historical simple result UI offered outcomes such as won/lost/stopped/deferred/converted_to_tender/converted_to_inquiry. `converted_to_contract` was intentionally excluded from the simple modal because the backend requires an actual linked contract.

## UI architecture lessons

PR55/56 established:

- management tools should not float over the notice list;
- selected actions must remain visible/stable;
- joining selected Case state must not scan/paginate the complete Tender/Inquiry archive;
- bounded Case-stage reads plus specific Notice detail are preferred;
- ambiguous duplicate row matching must not attach actions to the wrong record merely to increase coverage.

## Audit and history

Human recommendation dismissal, selection/removal, submission and result changes should leave appropriate persistent business/audit history. Do not conflate UI disappearance with record deletion.

## Future changes

Any new stage/result/action must be checked against:

- current model enums
- serializers/API requirements
- existing history/document constraints
- Direct vs Notice workflow differences
- human-review rules
- concurrent active session scope
