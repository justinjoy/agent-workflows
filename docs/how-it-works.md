# How It Works

## Implementation Skill

`implementation-skill` is a Datalog-selected harness for code changes. It turns
one implementation request into request facts, evaluates those facts with
PyreWire/Wirelog rules, and returns a machine-readable plan of atomic skills to
run.

Use it when the agent should not freely choose its own workflow. The harness
makes the selection explicit: trivial changes skip planning and review gates,
while non-trivial, cross-module, shared-behavior, or external-service changes
select planning, critique, review, broad validation, and final risk checks.

## Datalog Harness

The runtime package exposes:

```bash
agent-workflows-harness "refactor auth workflow and add tests"
```

The command emits JSON:

```json
{
  "request": {
    "request_id": "req",
    "request_type": "code_change",
    "properties": ["needs_tests", "non_trivial", "touches_shared_behavior"]
  },
  "selected": [
    {
      "order": 10,
      "skill_id": "inspect-repository",
      "reason": "code_change_requires_repository_context"
    }
  ],
  "blocked": []
}
```

Selection is computed by Wirelog rules through PyreWire, not by natural-language
skill descriptions.

The harness accepts only its documented request properties and the
`code_change` request type before generating Wirelog source. Unknown or malformed
facts fail with an input error. If a request contains both `trivial` and concrete
risk evidence such as `non_trivial`, shared behavior, external services, or
multi-file scope, the risk evidence wins and the trivial hint is removed.

Documentation-only requests still select `implement-atomic-change` and a
documentation-specific focused-validation reason. They skip planning and review
only when no separate risk fact requires those gates. Multi-file or explicitly
non-trivial documentation may still select the larger workflow, while
`docs_only` combined with external-service or shared-behavior impact is rejected
as contradictory input. Requests with no risk or documentation facts fail
closed to `non_trivial`.

Use `--decision-log path/to/decisions.jsonl` to append the request facts,
selected skills, blocked skills, and rule reasons as durable JSON Lines records.

The compatibility `implementation-skill` entrypoint remains stable for plugin
hosts. When the runtime command is unavailable, the skill fails closed by using
the non-trivial plan manually and reporting that the runtime selector could not
execute.

The Python runtime depends on `pyrewire>=1.0.4,<2.0`. Runtime-backed tests are
required and fail when PyreWire or its native Wirelog library cannot load; a
load failure is not treated as a skipped optional integration.

## Atomic Skills

The implementation harness can select these smaller skills:

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

## Persona Communication

![Implementation Skill persona communication diagram](assets/implementation-skill-communication.svg)

The Coordinator is the communication hub. It gathers repository context, runs
the selected atomic skills, sends each persona only the artifact needed for that
role, resolves disagreements, and keeps unrelated work out of scope.

The personas communicate through raw artifacts rather than shared assumptions:

- Architect returns a plan.
- Critic returns objections.
- Implementer returns a diff and validation output.
- Reviewer returns findings against the raw diff.
- Architect and Critic return final validation against the original goal.

## Roles

- **Architect** defines the intended behavior, affected files, interfaces, risks, tests, and atomic commit breakdown.
- **Critic** challenges the plan before code changes begin. It looks for hidden coupling, weak assumptions, over-broad scope, and tests that would not prove the behavior.
- **Implementer** changes the code in reviewable units and validates each unit before it is committed.
- **Reviewer** reviews the raw diff for bugs, regressions, missing tests, and scope creep.

The coordinating agent sequences those passes, resolves disagreements, and reports the result. It should not replace the role passes with its own unchecked judgment.

## Independence

The workflow depends on separation between roles:

- Architect and Critic should be independent so the critique is not just a confirmation of the plan.
- Implementer and Reviewer should be independent so the reviewer is not checking its own work.
- Final Architect and Critic validation confirms that the finished diff still matches the original goal and that accepted risks are deliberate.

When host-native independent agents are unavailable, the skill switches to degraded sequential mode. The workflow still runs the same gates, but the final report must say which independence guarantees were weakened.

## Atomic Changes

Implementation is split into commit-sized units. Each unit should have one behavioral purpose, touch only the files needed for that purpose, and leave the repository in a passing state after validation.

This keeps review focused and makes it easier to identify where a regression entered.

## When to Use It

Use `implementation-skill` for:

- behavior changes with multiple affected files
- risky refactors or migrations
- fixes where the failure mode is not obvious
- changes that need explicit test strategy
- PR feedback that requires implementation and review

For small edits, the Datalog selector should produce the small plan:
inspection, risk classification, atomic implementation, focused tests, and
reporting.

## Close Open Issues Goal

Explicitly invoke `$dev-workflows:close-open-issues-goal` or `/dev-workflows:close-open-issues-goal` (the host-specific form) only when you want to create, set, or start the persistent goal for reducing the current repository's open issue count to zero. Invocation creates the goal only: that same turn must not inspect or prioritize issues, implement work, close issues, or create issues unless those actions are separately requested.

When the goal is later executed, begin with the highest-priority open issue and resolve it using `$dev-workflows:implementation-skill` or `/dev-workflows:implementation-skill`. Work discovered while resolving an issue becomes a follow-up issue only after Architect and Critic have assessed it.

Each follow-up issue records:

- scope and intended outcome;
- discovery context or reproducible steps;
- acceptance criteria;
- priority rationale and dependencies, when known.

The goal has no default token budget; one is supplied only when explicitly requested. If another goal is already active, report that constraint and ask the user how to proceed. Do not replace, complete, or block the existing goal merely to create this one.
