# How It Works

## Implementation Skill

`implementation-skill` is a structured workflow for non-trivial code changes. It turns one implementation request into a sequence of independent checks so design, critique, code changes, review, and final validation do not collapse into one unexamined pass.

Use it when a change is large enough that mistakes could come from weak planning, hidden coupling, missing tests, or a reviewer simply confirming the implementer's assumptions.

## Persona Communication

![Implementation Skill persona communication diagram](assets/implementation-skill-communication.svg)

The Coordinator is the communication hub. It gathers repository context, sends each persona only the artifact needed for that role, resolves disagreements, and keeps unrelated work out of scope.

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

For small edits, direct implementation is usually enough.

## Close Open Issues Goal

Explicitly invoke `$dev-workflows:close-open-issues-goal` or `/dev-workflows:close-open-issues-goal` (the host-specific form) only when you want to create, set, or start the persistent goal for reducing the current repository's open issue count to zero. Invocation creates the goal only: that same turn must not inspect or prioritize issues, implement work, close issues, or create issues unless those actions are separately requested.

When the goal is later executed, begin with the highest-priority open issue and resolve it using `$dev-workflows:implementation-skill` or `/dev-workflows:implementation-skill`. Work discovered while resolving an issue becomes a follow-up issue only after Architect and Critic have assessed it.

Each follow-up issue records:

- scope and intended outcome;
- discovery context or reproducible steps;
- acceptance criteria;
- priority rationale and dependencies, when known.

The goal has no default token budget; one is supplied only when explicitly requested. If another goal is already active, report that constraint and ask the user how to proceed. Do not replace, complete, or block the existing goal merely to create this one.
