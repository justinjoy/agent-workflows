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

`critique_findings` must name the plan elements it examined -- the repository
paths or atomic units the `implementation_plan` proposed -- and which of the
categories above each was examined against. That holds for an accepted plan as
much as a rejected one: naming nothing is indistinguishable from not having
read the plan, and naming elements without saying what they were examined for
is indistinguishable from copying them out of the plan.

Do not manufacture objections to satisfy this. An acceptance that says what it
looked for and did not find is a complete critique; an invented defect is worse
than none, because the coordinator will act on it.

When a coordinator dispatched this skill, producing `critique_findings` is not
delivering it: return it the way that dispatch named. A pass that ends without
the coordinator holding it is a failed dispatch and its work is lost. Under
direct invocation the caller is the coordinator and delivery is immediate.
