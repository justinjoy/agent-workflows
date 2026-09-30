---
name: validate-final-design
description: Atomic implementation skill that validates the final diff against the intended architecture and user goal.
---

# Validate Final Design

Validate that the reviewed candidate matches the objective and intended design.
Always adjudicate `review_findings`. Use an implementation plan when one was
selected; otherwise use the objective, risk classification, exact candidate
diff, `approved_candidate_tree` ID, and test results.

This gate runs only after the review. When you received no `review_findings`,
or they echo a different `approved_candidate_tree` than the one you judge,
return `blocked` for that reason alone and judge nothing else. If you wrote
these `review_findings`, record every blocking finding as upheld.

Output `architect_validation` covering:

- an explicit `verdict` of `approved` or `blocked`
- the `approved_candidate_tree` ID being judged
- each finding the Reviewer marked `blocking`, upheld or overruled, with its
  reason; an overrule argues from the diff that the finding is wrong or not
  blocking, and any upheld blocking finding makes the verdict `blocked`
- behavior matches the objective
- commit or unit boundaries are coherent
- public contracts and docs are consistent

A `blocked` verdict must state its reasons and must be surfaced in
`report-result`. It stops the commit gate; it never ends the run silently.

Any candidate change invalidates this approval.

When a coordinator dispatched this skill, producing `architect_validation` is not
delivering it: return it the way that dispatch named. A pass that ends without
the coordinator holding it is a failed dispatch and its work is lost. Under
direct invocation the caller is the coordinator and delivery is immediate.
