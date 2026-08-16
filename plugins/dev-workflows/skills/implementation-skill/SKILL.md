---
name: implementation-skill
description: Wirelog-based implementation harness for code changes, evaluated through PyreWire. Invoke as $dev-workflows:implementation-skill in Codex or /dev-workflows:implementation-skill in Claude Code and Antigravity.
---

# Implementation Skill

## Overview

Use this compatibility entrypoint for code changes that should be handled by
the Wirelog-based agent workflow harness. The harness converts the request into
facts, evaluates Wirelog rules through PyreWire, and emits the atomic skills that
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
- `commit-atomic-change`
- `report-result`

The workflow still uses four roles when the selected plan requires them:

- **Architect**: define the intended design, scope, constraints, interfaces, and sequencing.
- **Critic**: challenge assumptions, find failure modes, and tighten the plan before implementation.
- **Implementer**: make changes in atomic commit-sized units with focused validation.
- **Reviewer**: review the Implementer's changes for bugs, regressions, missing tests, and scope creep.

## Wirelog Harness

Before editing, select the atomic skill plan with the runtime harness:

```bash
agent-workflows-harness "refactor auth workflow and add tests"
```

or pass explicit facts:

```bash
agent-workflows-harness --property non_trivial --property touches_shared_behavior --property needs_tests
```

Resolve the command without assuming the plugin host inherited an activated
Python environment. Use the first available option:

1. `agent-workflows-harness` when it is on `PATH`.
2. `<workspace>/.venv/bin/agent-workflows-harness` on POSIX or
   `<workspace>/.venv/Scripts/agent-workflows-harness.exe` on Windows when that
   file exists and is executable.
3. `python -m agent_workflows_harness.cli` when the active Python can import the
   package.

Run the resolved command and use its JSON output. Do not declare the runtime
unavailable merely because the bare command is absent from `PATH`; try the
remaining installed forms first. Do not install dependencies or rewrite the
host environment implicitly.

On success the command emits a machine-readable JSON plan containing request
facts, selected skills, blocked skills, and rule reasons, and exits `0`. Add
`--decision-log path/to/decisions.jsonl` to append a durable selection record.

A non-zero exit never prints a plan. Branch on the exit code rather than on the
shape of stdout, and never read a failure as an empty plan.

- exit `2`: rejected input. Stdout is empty and the cause is on stderr, so a
  caller reading only stdout sees nothing at all here. Fix the facts and run
  the selector again.
- exit `3`, `selector_unavailable`: the Wirelog runtime could not run. Fail
  closed as described below.
- exit `4`, `rule_conflict`: two rules disagree about the same skill, so no
  plan is deterministic. Do not fail closed to the non-trivial plan and do not
  proceed. Report the conflict through `report-result` and stop.
- exit `5`, `harness_error`: the harness failed for a reason it does not
  classify further. It is a harness defect, not a dead runtime and not bad
  input. Do not fail closed to the non-trivial plan; report it through
  `report-result` and stop.

Exits `3`, `4`, and `5` emit an `error` document carrying a `kind` on stdout;
exit `2` does not. Every one of these exits terminates the run and still
requires `report-result`. Producing no plan is never a reason to stop without
responding.

Skill choice is therefore made by explicit facts and Wirelog rules instead of by
free-form LLM tool selection.

If the harness runtime is unavailable in the host, fail closed: apply the
non-trivial plan manually, report that the runtime selector could not execute,
and do not skip planning, critique, review, or final validation gates.
Do not omit the commit gate after the candidate is approved.

## Workflow

### 1. Harness Selection

Determine request facts and run the Wirelog selector. Record the selected
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
objective; do not give it a plan to confirm. Dispatch it under Agent Use and
Degraded Mode: the pass is not complete until the coordinator holds
`implementation_plan`.

### 4. Critic Pass

Run this pass only when the selected skill plan includes `critique-plan`.
Before implementation, have the Critic challenge the Architect plan. Resolve
Critic objections before implementation. Dispatch it under Agent Use and
Degraded Mode: the pass is not complete until the coordinator holds
`critique_findings`.

### 5. Implementer Pass

Run `implement-atomic-change` in atomic units. This creates an uncommitted
atomic commit candidate; it must not create or amend a Git commit. Each unit
should:

- have one behavioral purpose
- be reviewable independently
- include tests or validation appropriate to risk
- leave the repo in a passing state after validation

Do not batch unrelated fixes into the same unit.

### 6. Validation

Run `run-focused-tests` when selected. Run `run-broad-tests` when the plan
selects it because shared behavior, public workflows, persistence, network, or
cross-module code changed.

### 7. Reviewer Pass

Every code change, including documentation-only and trivial changes, selects
`review-diff`. The Reviewer must not have written the change under review. Give
it the raw uncommitted diff, candidate path set and digest, and the objective,
not the Implementer's account. Every gate must identify the same
`approved_candidate_tree` created from the base tree with a temporary index.
Dispatch it under Agent Use and Degraded Mode: the pass is not complete until
the coordinator holds `review_findings`.

### 8. Architect and Critic Validation

Every code change selects `validate-final-design` and `validate-final-risks`.
Architect and Critic validate the same immutable candidate reviewed by the
Reviewer. When planning or plan critique was not selected, validate against the
objective, risk classification, tests, review findings, and exact candidate
instead. The candidate can proceed only when Reviewer, Architect, and Critic
agree there are no blocking issues.

Each gate returns an explicit `verdict` of `approved` or `blocked`. A `blocked`
verdict stops the commit gate for that candidate; it never ends the run
silently. Report the verdict and its reasons through `report-result`. Dispatch
both under Agent Use and Degraded Mode: neither pass is complete until the
coordinator holds `architect_validation` and `critic_validation` echoing the
`approved_candidate_tree` they judged.

Any fix invalidates prior test, review, and final validation artifacts. Repeat
the selected validation, independent review, and final validation gates for the
changed candidate.

### 9. Commit

Run `commit-atomic-change` only after all selected validation passes and
Reviewer, Architect, and Critic approve the same candidate. Require a clean real
index before staging; do not unstage or repair pre-existing entries. Stage only
the approved paths and hunks, verify the staged tree matches
`approved_candidate_tree`, create a new commit without bypassing hooks or
amending history, and verify the commit tree matches the approved tree.

For multiple atomic units, repeat implementation through commit for each unit.

Run `report-result` once on every termination of the run, not only after a
successful commit. A blocking gate verdict, an unavailable runtime, a rule
conflict, a harness defect, or an abandoned unit still terminates the run and
still requires the report.

## Agent Use and Degraded Mode

Independent role passes are the normal workflow. A role that inherits another
role's reasoning can merely confirm it, which defeats the critique and review
gates.

Confirm receipt before treating any dispatched pass as complete. A pass is
complete only when the coordinator holds that role's named artifact and the
artifact echoes the identifiers its skill requires, such as the
`approved_candidate_tree` ID a validation gate judged. Work the coordinator
never received was not delivered, and a verdict that echoes nothing it judged
is not evidence the role saw the candidate. Requiring an artifact without
requiring that substance only trades a silent loss for a rubber stamp.

Artifacts do not come back the same way in every host. Identify how a
dispatched role's output actually reaches the coordinator before the first
dispatch, and name it in every dispatch prompt together with the artifact the
role must return.

A role that ends, goes idle, or reports itself available without the
coordinator holding its artifact is a failed dispatch, not a completed pass.
So is a bound the coordinator set before dispatching that elapses with nothing
delivered. Treat either exactly as an error; waiting on a role that already
stopped is the hang this rule exists to prevent.

Re-dispatch a failed role at most once, and only when something material
changes: naming a return path the lost prompt omitted, a different agent, or a
synchronous dispatch. Re-sending an identical prompt carries no new
information, so degrade instead.

If the re-dispatch also delivers nothing, degrade that role alone and keep
every other role independent. While other agents can still be reached, no
single agent may hold both sides of a gate pair -- Architect and Critic,
Implementer and Reviewer, or Implementer and final validation -- so re-dispatch
to a different agent rather than absorbing the role. If independent agents are
unavailable in the host at all, that pairing rule cannot apply and the whole
remaining workflow drops to degraded sequential mode instead. Preserve and use
every successfully returned raw artifact; if a lost one arrives after the gate
ran, use what was held at gate time and report the duplicate.

Degraded mode weakens independence guarantees. It must not omit review, final
validation, or commit gates. The final handoff must name every dispatch that
delivered nothing, every role that ran degraded, and why.

## Completion Checklist

Before final response, verify:

- The Wirelog selector ran and emitted a plan, or runtime unavailability was
  declared with the fail-closed plan, or a rule conflict was reported and the
  run stopped without editing.
- The final response reports selected atomic skills and rule reasons.
- Independent Architect and Critic passes ran when selected, or degraded mode
  and its cause were declared.
- Every dispatched role's artifact reached the coordinator, or the failed
  dispatch, what changed on any re-dispatch, and the role that ran degraded as
  a result were all recorded. A role that delivered nothing and was not
  recorded is a silent termination, not a completed pass.
- Every gate verdict that ran appears in the final response. Running a gate and
  omitting its verdict is a silent termination, not a completed run.
- Critic risks were addressed or explicitly accepted.
- Implementation was divided into atomic commit-sized changes.
- Tests or validation were run and reported.
- Reviewer checked the raw candidate diff.
- Architect and Critic agreed the same candidate satisfies the goal.
- Each approved candidate was committed atomically and its commit tree matches
  the approved tree.
- Unrelated untracked or modified files were not included.

In the final response, report:

- selected skill plan, plus blocked skills and their rule reasons, or the
  selector `error.kind` and exit code when the run produced no plan
- `implementation_plan` summary and `critique_findings` when those skills were selected
- `review_findings`
- `architect_validation` and `critic_validation`, each with its explicit `verdict`
  and the `approved_candidate_tree` ID it judged
- every atomic commit hash, subject, committed paths, and approved digest
- PR URL if opened
- validation commands and results
- remaining untracked/unrelated files, if any
- every role dispatch that delivered no artifact, what changed on any
  re-dispatch, and which roles ran degraded as a result
- whether degraded sequential mode covered the whole run, and every
  independence guarantee that weakened
