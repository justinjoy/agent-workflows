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

When a coordinator dispatched this skill, producing `critique_findings` is not
delivering it: return it the way that dispatch named. A pass that ends without
the coordinator holding it is a failed dispatch and its work is lost. Under
direct invocation the caller is the coordinator and delivery is immediate.
