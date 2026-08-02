---
name: run-broad-tests
description: Atomic implementation skill that runs broader validation when shared behavior, public workflows, or cross-module changes are touched.
---

# Run Broad Tests

Run broader validation when the Wirelog harness selects this skill.

Output `broad_test_result` with:

- command or validation performed
- pass/fail status
- affected workflow or shared behavior coverage
- the `approved_candidate_tree` ID validated by this result
