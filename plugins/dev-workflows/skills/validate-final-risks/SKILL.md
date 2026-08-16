---
name: validate-final-risks
description: Atomic implementation skill that validates accepted risks and prior critique findings before completion.
---

# Validate Final Risks

Validate that review findings and known risks were addressed or deliberately
accepted. Use prior critique findings when a critique was selected; otherwise
evaluate the objective, risk classification, exact candidate diff,
`approved_candidate_tree` ID, test results, review findings, and unrelated-work
exclusion directly.

Output `critic_validation` covering:

- an explicit `verdict` of `approved` or `blocked`
- the `approved_candidate_tree` ID being judged
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
