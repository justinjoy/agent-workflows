# How It Works

## Implementation Skill

`implementation-skill` is a structured workflow for non-trivial code changes. It turns one implementation request into a sequence of independent checks so design, critique, code changes, review, and final validation do not collapse into one unexamined pass.

Use it when a change is large enough that mistakes could come from weak planning, hidden coupling, missing tests, or a reviewer simply confirming the implementer's assumptions.

## Flow

```mermaid
flowchart TD
  User[User request] --> Intake[Intake<br/>repo state, scope, constraints]
  Intake --> Architect[Architect<br/>design and atomic plan]
  Architect --> Critic[Critic<br/>attack assumptions and risks]
  Critic --> Decision{Plan ready?}
  Decision -- No --> Architect
  Decision -- Yes --> Implementer[Implementer<br/>one atomic unit at a time]
  Implementer --> Tests[Focused validation<br/>then broader checks if needed]
  Tests --> Reviewer[Reviewer<br/>raw diff review]
  Reviewer --> Findings{Blocking findings?}
  Findings -- Yes --> Implementer
  Findings -- No --> FinalCheck[Architect + Critic validation]
  FinalCheck --> Done[Done<br/>report commits and validation]
```

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
