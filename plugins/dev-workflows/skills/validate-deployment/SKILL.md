---
name: validate-deployment
description: Validate deployment risks selected by the ontology pack before review and commit.
---

# Validate Deployment

Run when the selected plan includes `validate-deployment`. Inputs are the objective,
changed paths and raw diff, derived risk facts, and `approved_candidate_tree`.
Perform these checks against that exact candidate after focused/broad tests and
before `review-diff`:

- Validate changed manifests, pipeline syntax and runtime configuration with the repository's tools.
- Check build artifacts, deployment prerequisites and health checks in a local or isolated environment.
- Verify the release/rollback procedure and configuration compatibility; record platform-specific assumptions.

Use repository tests, static analysis and disposable isolated environments.
Selection does not authorize deployment, production data changes or access to
real secrets. Use synthetic data and do not include secrets in evidence.

Return `deployment_validation` with the `approved_candidate_tree`, checked paths, commands
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
