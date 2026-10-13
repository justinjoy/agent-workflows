---
name: validate-data-change
description: Validate data change risks selected by the ontology pack before review and commit.
---

# Validate Data Change

Run when the selected plan includes `validate-data-change`. Inputs are the objective,
changed paths and raw diff, derived risk facts, and `approved_candidate_tree`.
Perform these checks against that exact candidate after focused/broad tests and
before `review-diff`:

- Test schema and data compatibility with supported old/new readers and writers.
- Exercise backfill restart, interruption and idempotency using disposable fixtures.
- Verify destructive-change safeguards and a rollback or backup/restore path; record limits when a migration is intentionally irreversible.

Use repository tests, static analysis and disposable isolated environments.
Selection does not authorize deployment, production data changes or access to
real secrets. Use synthetic data and do not include secrets in evidence.

Return `data_change_validation` with the `approved_candidate_tree`, checked paths, commands
and results, uncovered risks, and an explicit `verdict` of `approved` or
`blocked`. Approve only when every applicable check is supported by evidence;
explain why a check does not apply instead of silently skipping it. If required
validation cannot run, record the unavailable environment and return `blocked`.
A failed or missing result blocks the commit gate and must appear in
`report-result`. Any candidate change invalidates this artifact.

The coordinator may perform this validation as Implementer; it does not replace
the independent Reviewer, Architect or Critic gates. Return the named artifact
to the coordinator through the delivery path specified in the dispatch, or
directly to the caller when invoked directly.
