---
name: validate-final-design
description: Atomic implementation skill that validates the final diff against the intended architecture and user goal.
---

# Validate Final Design

Validate that the reviewed candidate matches the objective and intended design.
Use an implementation plan when one was selected; otherwise use the objective,
risk classification, exact candidate diff, `approved_candidate_tree` ID, test
results, and review findings.

Output `architect_validation` covering:

- an explicit `verdict` of `approved` or `blocked`
- the `approved_candidate_tree` ID being judged
- behavior matches the objective
- commit or unit boundaries are coherent
- public contracts and docs are consistent

A `blocked` verdict must state its reasons and must be surfaced in
`report-result`. It stops the commit gate; it never ends the run silently.

Any candidate change invalidates this approval.
