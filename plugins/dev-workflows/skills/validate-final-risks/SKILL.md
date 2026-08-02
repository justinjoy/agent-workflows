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

- the `approved_candidate_tree` ID being approved
- prior objections
- known failure modes
- validation evidence
- unrelated work exclusion

Any candidate change invalidates this approval.
