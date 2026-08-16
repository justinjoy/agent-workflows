---
name: create-implementation-plan
description: Atomic implementation skill that creates a plan for non-trivial changes selected by the Wirelog harness.
---

# Create Implementation Plan

Create an `implementation_plan` artifact for a non-trivial or risky change.

The plan should identify:

- user-visible behavior to change
- affected modules and contracts
- data model, migration, or compatibility concerns
- test strategy and edge cases
- atomic implementation units

When a coordinator dispatched this skill, producing `implementation_plan` is not
delivering it: return it the way that dispatch named. A pass that ends without
the coordinator holding it is a failed dispatch and its work is lost. Under
direct invocation the caller is the coordinator and delivery is immediate.
