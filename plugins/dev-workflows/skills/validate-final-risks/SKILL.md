---
name: validate-final-risks
description: Atomic implementation skill that validates accepted risks and prior critique findings before completion.
---

# Validate Final Risks

Validate that review findings and known risks were addressed or deliberately
accepted. Always adjudicate `review_findings`. Use prior critique findings when
a critique was selected; otherwise evaluate the objective, risk
classification, exact candidate diff, `approved_candidate_tree` ID, test
results, and unrelated-work exclusion directly.

This gate runs only after the review. When you received no `review_findings`,
or they echo a different `approved_candidate_tree` than the one you judge,
return `blocked` for that reason alone and judge nothing else. If you wrote
these `review_findings`, record every blocking finding as upheld.

Output `critic_validation` covering:

- an explicit `verdict` of `approved` or `blocked`
- the `approved_candidate_tree` ID being judged
- each finding the Reviewer marked `blocking`, upheld or overruled, with its
  reason; an overrule argues from the diff that the finding is wrong or not
  blocking, and any upheld blocking finding makes the verdict `blocked`
- prior objections
- known failure modes
- validation evidence
- unrelated work exclusion

A `blocked` verdict must state its reasons and must be surfaced in
`report-result`. It stops the commit gate; it never ends the run silently.

Any candidate change invalidates this approval.

When a coordinator dispatched this skill, producing `critic_validation` is not
delivering it: return it the way that dispatch named. A pass that ends without
the coordinator holding it is a failed dispatch and its work is lost. Under
direct invocation the caller is the coordinator and delivery is immediate.
