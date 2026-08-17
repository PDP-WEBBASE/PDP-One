# PDP One — Direct Opportunities

## Current accepted workflow

`All Direct Opportunities → Selected → Submitted → Results`

PR57 removed the separate Direct `Recommended` tab. Direct opportunities are reviewed from the full list and explicitly selected by the user.

## Selected actions

PR56/57 aligned Direct Opportunity selected actions with the broader procurement workflow:

- select from All;
- remove from selected according to safe workflow state;
- manage submission documents using the shared submission-document infrastructure;
- record submission, including zero-file submission;
- register result.

Do not build a parallel file-storage path merely because the entity is Direct Opportunity.

## Results

Historical PR57 simple result UI supported outcomes such as won, lost, stopped, deferred, converted_to_tender and converted_to_inquiry.

`converted_to_contract` was intentionally not offered in the simple modal because the backend requires a real contract linkage. A future implementation must provide a valid contract picker/creation workflow rather than posting an incomplete outcome.

## Preservation

Removing workflow selection must not delete the underlying Direct Opportunity record or relevant history.
