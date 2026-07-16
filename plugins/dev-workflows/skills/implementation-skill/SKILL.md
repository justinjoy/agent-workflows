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

Each role runs as its own subagent. The main agent owns this skill, sequences the passes, and integrates results; it does not perform a role pass itself. Dispatch every Architect, Critic, Implementer, and Reviewer pass to a dedicated subagent so each role reasons from its own context and cannot rationalize a prior role's conclusion. See [Subagent Use](#subagent-use) for dispatch rules and the fallback when subagents are unavailable.

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

Dispatch an Architect subagent to produce a short implementation plan before any editing. Give it the intake findings and the objective; do not give it a plan to confirm. The Architect should identify:

- the user-visible behavior to change
- affected modules and ownership boundaries
- data model or API contract changes
- migration/backward compatibility concerns
- test strategy and likely edge cases
- an atomic commit breakdown

Prefer the repository's existing patterns. Avoid broad refactors unless required for the requested behavior.

### 3. Critic Pass

Dispatch a Critic subagent to attack the Architect plan before implementation. Pass it the plan and the repository context, not the Architect's justification for the plan. The Critic should look for:

- hidden coupling between modules
- unsafe assumptions about state, concurrency, persistence, or external services
- missing failure handling
- tests that would pass without proving the behavior
- over-broad scope or non-atomic change boundaries

Resolve Critic objections before implementation. If Architect and Critic disagree, state the tradeoff and choose the smaller safer path unless the user requested a broader design.

### 4. Implementer Pass

Dispatch an Implementer subagent per atomic unit, giving it the agreed plan and that unit's boundary. Run implementer subagents sequentially when units touch shared files; run them concurrently only when their file sets are disjoint. An atomic unit should:

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

Dispatch a Reviewer subagent to review the Implementer's diff before declaring work complete. The Reviewer must be a fresh subagent that did not write the code — never the Implementer subagent, and never the main agent. Give it the diff and the objective, not the Implementer's account of what it did. The Reviewer should use a code-review stance:

- findings first, ordered by severity
- cite concrete files/lines where possible
- focus on bugs, regressions, missing tests, and maintainability risks
- avoid praise and summary-only review

If issues are found, send the work back to Implementer for another atomic fix and repeat validation.

### 6. Architect and Critic Validation

After Reviewer approval, dispatch Architect and Critic subagents to validate the final diff against the original goal. Reuse the original Architect and Critic subagents so they carry their own prior reasoning; if they are gone, dispatch fresh ones with the original plan and the recorded objections.

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

Every role pass is a subagent dispatch. The separation is the point: a role that inherits another role's reasoning will agree with it, which defeats the critique and review gates.

Dispatch rules:

- One subagent per role pass. Do not merge Architect and Critic into one call, or let the Implementer review its own diff.
- Keep prompts scoped. Provide raw artifacts (plan, diff, test output, objective) and let the subagent reach its own conclusion. Never state the expected answer or the prior role's rationale.
- Have each subagent return findings the main agent can act on: the plan, the objection list, the diff and validation results, or the ordered review findings.
- The main agent sequences passes, resolves disagreements, and reports to the user. It does not perform role passes.
- Do not delegate reading skill instructions. The main agent remains responsible for applying this skill.

If subagents are unavailable, say so explicitly in the final response, then simulate the roles sequentially in the main thread with clearly labeled role outputs. This is a degraded mode: the reviewer and critic gates are weaker because one context produces both the work and its critique, so weight their approval accordingly.

## Completion Checklist

Before final response, verify:

- Each role pass ran as its own subagent, or the degraded single-thread mode was declared.
- Architect plan was considered.
- Critic risks were addressed or explicitly accepted.
- Implementation was divided into atomic commit-sized changes.
- Tests or validation were run and reported.
- Reviewer checked the final diff and did not write the code under review.
- Architect and Critic agreed the result satisfies the goal.
- Unrelated untracked or modified files were not included.

In the final response, report:

- commit hashes if commits were made
- PR URL if opened
- validation commands and results
- remaining untracked/unrelated files, if any
