---
name: implementation-skill
description: Host-neutral workflow for non-trivial changes requiring independent architecture, critique, implementation, review, atomic commits, and consensus. Invoke as $dev-workflows:implementation-skill in Codex, /dev-workflows:implementation-skill in Claude Code, or /dev-workflows:implementation-skill (or implementation-skill) in Antigravity.
---

# Implementation Skill

## Overview

Use this skill for substantial code changes where correctness depends on explicit design analysis, critique, incremental implementation, and review consensus. The workflow uses four roles:

- **Architect**: define the intended design, scope, constraints, interfaces, and sequencing.
- **Critic**: challenge assumptions, find failure modes, and tighten the plan before implementation.
- **Implementer**: make changes in atomic commit-sized units with focused validation.
- **Reviewer**: review the Implementer's changes for bugs, regressions, missing tests, and scope creep.

In Codex, invoke this skill as `$dev-workflows:implementation-skill`; in Claude Code or Antigravity, invoke it as `/dev-workflows:implementation-skill` (or `implementation-skill`).

Use the host's native independent agents for every role pass when they are available. The coordinating agent sequences the passes and integrates their raw artifacts; it does not substitute its own role pass. Architect and Critic must be independent of one another, and a Reviewer must not be the agent that wrote the code. See [Agent Use and Degraded Mode](#agent-use-and-degraded-mode) for the required fallback.

## Workflow

### 1. Intake

Clarify the concrete target only when it is genuinely ambiguous. Otherwise infer the smallest useful scope from the request and repository context.

Inspect the codebase before proposing implementation details:

- current branch and worktree state
- relevant files, tests, and local patterns
- open PR/issue context if the user references one
- existing constraints from project docs or tests

Protect unrelated work. Do not stage, revert, or modify unrelated files.

### 2. Architect Pass

Ask an independent Architect agent to produce a short implementation plan before any editing. Give it the intake findings and the objective; do not give it a plan to confirm. The Architect should identify:

- the user-visible behavior to change
- affected modules and ownership boundaries
- data model or API contract changes
- migration/backward compatibility concerns
- test strategy and likely edge cases
- an atomic commit breakdown

Prefer the repository's existing patterns. Avoid broad refactors unless required for the requested behavior.

### 3. Critic Pass

Ask an independent Critic agent to attack the Architect plan before implementation. Pass it the plan and the repository context, not the Architect's justification for the plan. The Critic must be distinct from the Architect. It should look for:

- hidden coupling between modules
- unsafe assumptions about state, concurrency, persistence, or external services
- missing failure handling
- tests that would pass without proving the behavior
- over-broad scope or non-atomic change boundaries

Resolve Critic objections before implementation. If Architect and Critic disagree, state the tradeoff and choose the smaller safer path unless the user requested a broader design.

### 4. Implementer Pass

Ask an independent Implementer agent per atomic unit, giving it the agreed plan and that unit's boundary. Run implementation sequentially when units touch shared files; use concurrent agents only when their file sets are confirmed disjoint. An atomic unit should:

- have one behavioral purpose
- be reviewable independently
- include tests or validation appropriate to risk
- leave the repo in a passing state when committed

For each atomic unit:

1. Edit only the files needed for that unit.
2. Run focused tests first.
3. Run broader tests when shared behavior or public workflows changed.
4. Commit with a terse message after validation.

Do not batch unrelated fixes into the same commit. If a necessary prerequisite appears, make it a separate atomic unit or explain why it is inseparable.

### 5. Reviewer Pass

Ask an independent Reviewer agent to review the Implementer's diff before declaring work complete. The Reviewer must not have written the code under review. Give it the raw diff and the objective, not the Implementer's account of what it did. The Reviewer should use a code-review stance:

- findings first, ordered by severity
- cite concrete files/lines where possible
- focus on bugs, regressions, missing tests, and maintainability risks
- avoid praise and summary-only review

If issues are found, send the work back to Implementer for another atomic fix and repeat validation.

### 6. Architect and Critic Validation

After Reviewer approval, ask independent Architect and Critic agents to validate the final diff against the original goal. Prefer the original Architect and Critic agents so each can compare the final result with its own raw artifact; if unavailable, use fresh independent agents with the original plan and recorded objections.

The Architect confirms:

- the implemented design matches the intended behavior
- the commit boundaries are coherent
- public contracts and docs are consistent

The Critic confirms:

- prior objections were addressed
- known failure modes are tested or deliberately accepted
- no unrelated work was included

The task is complete only when Reviewer, Architect, and Critic agree there are no blocking issues.

## Agent Use and Degraded Mode

Independent role passes are the normal workflow. A role that inherits another role's reasoning can merely confirm it, which defeats the critique and review gates.

Normal-mode rules:

- Use one host-native independent agent per role pass. Do not combine Architect and Critic, and do not let an Implementer review its own diff.
- Keep prompts scoped. Provide raw artifacts (objective, intake, plan, objections, diff, and test output) and let the receiving agent reach its own conclusion. Never state the expected answer or another role's rationale.
- Require each agent to return an actionable raw artifact: plan, objection list, implementation diff and validation results, or findings ordered by severity.
- Coordinate mutation of shared files sequentially. Concurrent work is allowed only after confirming each agent's file set is disjoint.
- The coordinating agent sequences passes, resolves disagreements, and reports to the user. It does not delegate reading this skill's instructions.

If independent agents are unavailable in the current host, or dispatch fails for any role, immediately switch the remaining workflow to **degraded sequential mode**. Preserve and use every successfully returned raw artifact. Complete each remaining pass sequentially in the coordinating context, with clearly labeled `Architect (degraded)`, `Critic (degraded)`, `Implementer (degraded)`, or `Reviewer (degraded)` outputs. Do not retry a failed dispatch in a way that abandons the evidence already collected.

Degraded mode weakens independence guarantees: Architect and Critic may share a context, and the Reviewer may be unable to be independent of the Implementer. The final handoff must explicitly name which role separations were weakened and why. Keep all other gates — raw-artifact review, tests, atomic commits, scope checks, and final Architect/Critic validation — in force.

## Completion Checklist

Before final response, verify:

- Independent Architect and Critic passes ran, or degraded sequential mode and its cause were declared.
- Architect plan was considered.
- Critic risks were addressed or explicitly accepted.
- Implementation was divided into atomic commit-sized changes.
- Tests or validation were run and reported.
- Reviewer checked the raw final diff and did not write the code under review, or the weakened separation was declared in degraded mode.
- Architect and Critic agreed the result satisfies the goal.
- Unrelated untracked or modified files were not included.

In the final response, report:

- commit hashes if commits were made
- PR URL if opened
- validation commands and results
- remaining untracked/unrelated files, if any
- whether degraded sequential mode was used and every independence guarantee it weakened
