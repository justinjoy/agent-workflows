---
name: critique-plan
description: Atomic implementation skill that challenges a selected implementation plan before edits begin.
---

# Critique Plan

Review the `implementation_plan` artifact before implementation.

Output `critique_findings` focused on:

- hidden coupling
- unsafe state, concurrency, persistence, or external-service assumptions
- weak failure handling
- tests that would pass without proving behavior
- over-broad or non-atomic change boundaries
