---
name: implementation-skill
description: Datalog/PyreWire-selected implementation harness for code changes. Invoke as $dev-workflows:implementation-skill in Codex, /dev-workflows:implementation-skill in Claude Code, or /dev-workflows:implementation-skill (or implementation-skill) in Antigravity.
---

# Implementation Skill

## Overview

Use this compatibility entrypoint for code changes that should be handled by
the Datalog-based agent workflow harness. The harness converts the request into
facts, evaluates the PyreWire/Wirelog selector, and emits the atomic skills that
the coordinator is allowed to run for the current request.

The old monolithic procedure is now split into smaller skills:

- `inspect-repository`
- `classify-change-risk`
- `create-implementation-plan`
- `critique-plan`
- `implement-atomic-change`
- `run-focused-tests`
- `run-broad-tests`
- `review-diff`
- `validate-final-design`
- `validate-final-risks`
- `report-result`

The workflow still uses four roles when the selected plan requires them:

- **Architect**: define the intended design, scope, constraints, interfaces, and sequencing.
- **Critic**: challenge assumptions, find failure modes, and tighten the plan before implementation.
- **Implementer**: make changes in atomic commit-sized units with focused validation.
- **Reviewer**: review the Implementer's changes for bugs, regressions, missing tests, and scope creep.

## Datalog Harness

Before editing, select the atomic skill plan with the runtime harness:

```bash
agent-workflows-harness "refactor auth workflow and add tests"
```

or pass explicit facts:

```bash
agent-workflows-harness --property non_trivial --property touches_shared_behavior --property needs_tests
```

The command emits a machine-readable JSON plan containing request facts,
selected skills, blocked skills, and rule reasons. Add
`--decision-log path/to/decisions.jsonl` to append a durable selection record.
Skill choice is therefore made by explicit facts and Wirelog rules instead of by
free-form LLM tool selection.

If the harness runtime is unavailable in the host, fail closed: apply the
non-trivial plan manually, report that the runtime selector could not execute,
and do not skip planning, critique, review, or final validation gates.

## Workflow

### 1. Harness Selection

Determine request facts and run the Datalog selector. Record the selected
skills and their rule reasons in the final response.

Minimum facts include:

- request type
- trivial or non-trivial risk
- single-file or multi-file scope
- test need
- review need
- shared behavior, public API, persistence, network, or workflow impact

### 2. Intake

Clarify the concrete target only when it is genuinely ambiguous. Otherwise
infer the smallest useful scope from the request and repository context.

Inspect the codebase before proposing implementation details:

- current branch and worktree state
- relevant files, tests, and local patterns
- open PR/issue context if the user references one
- existing constraints from project docs or tests

Protect unrelated work. Do not stage, revert, or modify unrelated files.

### 3. Architect Pass

Run this pass only when the selected skill plan includes
`create-implementation-plan`. Ask an independent Architect agent to produce a
short implementation plan before editing. Give it the intake findings and the
objective; do not give it a plan to confirm.

### 4. Critic Pass

Run this pass only when the selected skill plan includes `critique-plan`.
Before implementation, have the Critic challenge the Architect plan. Resolve
Critic objections before implementation.

### 5. Implementer Pass

Run `implement-atomic-change` in atomic units. Each unit should:

- have one behavioral purpose
- be reviewable independently
- include tests or validation appropriate to risk
- leave the repo in a passing state when committed

Do not batch unrelated fixes into the same unit.

### 6. Validation

Run `run-focused-tests` when selected. Run `run-broad-tests` when the plan
selects it because shared behavior, public workflows, persistence, network, or
cross-module code changed.

### 7. Reviewer Pass

Run this pass only when the selected skill plan includes `review-diff`. The
Reviewer must not have written the code under review. Give it the raw diff and
the objective, not the Implementer's account.

### 8. Architect and Critic Validation

Run these passes only when the selected skill plan includes
`validate-final-design` and `validate-final-risks`. The task is complete only
when Reviewer, Architect, and Critic agree there are no blocking issues, or
degraded mode and accepted risks are explicitly reported.

## Agent Use and Degraded Mode

Independent role passes are the normal workflow. A role that inherits another
role's reasoning can merely confirm it, which defeats the critique and review
gates.

If independent agents are unavailable in the current host, or dispatch fails for
any selected role, immediately switch the remaining workflow to degraded
sequential mode. Preserve and use every successfully returned raw artifact.

Degraded mode weakens independence guarantees. The final handoff must
explicitly name which role separations were weakened and why.

## Completion Checklist

Before final response, verify:

- The Datalog selector ran and emitted a plan, or runtime unavailability was
  declared with the fail-closed plan.
- The final response reports selected atomic skills and rule reasons.
- Independent Architect and Critic passes ran when selected, or degraded mode
  and its cause were declared.
- Critic risks were addressed or explicitly accepted.
- Implementation was divided into atomic commit-sized changes.
- Tests or validation were run and reported.
- Reviewer checked the raw final diff when selected.
- Architect and Critic agreed the result satisfies the goal when selected.
- Unrelated untracked or modified files were not included.

In the final response, report:

- selected skill plan
- commit hashes if commits were made
- PR URL if opened
- validation commands and results
- remaining untracked/unrelated files, if any
- whether degraded sequential mode was used and every independence guarantee it weakened
