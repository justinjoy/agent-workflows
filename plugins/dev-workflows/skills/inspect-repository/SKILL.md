---
name: inspect-repository
description: Atomic implementation skill that gathers branch, worktree, relevant files, tests, and local project constraints before code changes.
---

# Inspect Repository

Gather the repository context needed for one implementation run:

- current branch and worktree state
- relevant source files, tests, and local patterns
- referenced issue, pull request, or documentation context
- constraints that protect unrelated user work

Output a concise `repository_context` artifact for later skills.
