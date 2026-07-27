---
name: close-open-issues-goal
description: Create a persistent goal for reducing a repository's open issue count to zero with priority-first resolution and self-contained follow-up issues. Use when the user explicitly asks to create, set, or start this open-issues resolution goal; do not use to begin resolving issues without an explicit goal-creation request.
---

# Close Open Issues Goal

Create the goal only. Do not inspect, prioritize, implement, close, or create repository issues in the same turn unless the user separately asks to begin execution.

## Workflow

1. Confirm that the user explicitly asks to create this goal. If they only ask to resolve issues, follow their request without calling `create_goal`.
2. Create a goal with this objective, adapting only the repository identifier when the user supplied one:

   ```text
   Reduce the current repository's open issue count to zero. Select the highest-priority open issue first and resolve it using $dev-workflows:implementation-skill. When new work is discovered, have Architect and Critic discuss it, then register a self-contained follow-up issue containing scope, reproduction or discovery context, and acceptance criteria.
   ```

3. Do not set `token_budget` unless the user explicitly provides one.
4. If an active goal prevents creation, report that constraint and ask the user how to handle the existing goal. Do not replace, complete, or block it merely to create this one.
5. Report the created objective and active status concisely.

## Follow-up Issue Requirements

When this goal is later executed, create a follow-up issue only after Architect and Critic have assessed the newly discovered work. Require every follow-up issue to state:

- scope and intended outcome;
- discovery context or reproducible steps;
- acceptance criteria;
- priority rationale and dependencies, when known.
