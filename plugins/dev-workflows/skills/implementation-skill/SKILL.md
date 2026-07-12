---
name: implementation-skill
description: Structured implementation workflow for non-trivial coding tasks that require role-based analysis, atomic commits, review, and consensus. Use when the user asks Codex to use Implementation Skill, asks for architect/critic/implementer/reviewer personas, requests atomic implementation commits, or wants subagent-assisted planning, implementation, and review before completion.
---

# Implementation Skill

## Overview

Use this skill for substantial code changes where correctness depends on explicit design analysis, critique, incremental implementation, and review consensus. The workflow uses four roles:

- **Architect**: define the intended design, scope, constraints, interfaces, and sequencing.
- **Critic**: challenge assumptions, find failure modes, and tighten the plan before implementation.
- **Implementer**: make changes in atomic commit-sized units with focused validation.
- **Reviewer**: review the Implementer's changes for bugs, regressions, missing tests, and scope creep.

Subagents are allowed when available. Use them to run independent Architect, Critic, Implementer, or Reviewer passes when the task is large enough to benefit from separation.

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

Produce a short implementation plan before editing when the change is non-trivial. The Architect should identify:

- the user-visible behavior to change
- affected modules and ownership boundaries
- data model or API contract changes
- migration/backward compatibility concerns
- test strategy and likely edge cases
- an atomic commit breakdown

Prefer the repository's existing patterns. Avoid broad refactors unless required for the requested behavior.

### 3. Critic Pass

Before implementation, have the Critic challenge the Architect plan. The Critic should look for:

- hidden coupling between modules
- unsafe assumptions about state, concurrency, persistence, or external services
- missing failure handling
- tests that would pass without proving the behavior
- over-broad scope or non-atomic change boundaries

Resolve Critic objections before implementation. If Architect and Critic disagree, state the tradeoff and choose the smaller safer path unless the user requested a broader design.

### 4. Implementer Pass

Implement in atomic units. An atomic unit should:

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

Review the Implementer's diff before declaring work complete. The Reviewer should use a code-review stance:

- findings first, ordered by severity
- cite concrete files/lines where possible
- focus on bugs, regressions, missing tests, and maintainability risks
- avoid praise and summary-only review

If issues are found, send the work back to Implementer for another atomic fix and repeat validation.

### 6. Architect and Critic Validation

After Reviewer approval, the Architect and Critic must both validate the final diff against the original goal.

The Architect confirms:

- the implemented design matches the intended behavior
- the commit boundaries are coherent
- public contracts and docs are consistent

The Critic confirms:

- prior objections were addressed
- known failure modes are tested or deliberately accepted
- no unrelated work was included

The task is complete only when Reviewer, Architect, and Critic agree there are no blocking issues.

## Subagent Use

Use subagents when separation improves quality or when the user explicitly permits it. Good uses:

- ask an Architect subagent for a design plan from repository context
- ask a Critic subagent to attack the plan before edits
- ask a Reviewer subagent to review the final diff independently
- ask an Implementer subagent to handle a clearly bounded atomic unit

Keep subagent prompts scoped. Provide raw artifacts and the target objective, not the expected answer. Do not delegate reading skill instructions; the main agent remains responsible for applying this skill.

If subagents are unavailable, simulate the roles sequentially in the main thread and label the role outputs clearly.

## Completion Checklist

Before final response, verify:

- Architect plan was considered.
- Critic risks were addressed or explicitly accepted.
- Implementation was divided into atomic commit-sized changes.
- Tests or validation were run and reported.
- Reviewer checked the final diff.
- Architect and Critic agreed the result satisfies the goal.
- Unrelated untracked or modified files were not included.

In the final response, report:

- commit hashes if commits were made
- PR URL if opened
- validation commands and results
- remaining untracked/unrelated files, if any
