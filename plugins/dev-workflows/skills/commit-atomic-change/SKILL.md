---
name: commit-atomic-change
description: Atomic implementation skill that commits one reviewed and approved change without including unrelated work.
---

# Commit Atomic Change

Commit one immutable atomic candidate only after all selected gates succeed.

Required evidence:

- focused tests passed
- broad tests passed when selected
- independent review has no blocking findings
- Architect design validation passed
- Critic risk validation passed
- every gate artifact identifies the same `approved_candidate_tree` ID created
  from the base tree with a temporary index
- the `code_diff` and review artifacts also identify the approved path set and
  content digest

Before committing:

1. Require a completely clean real index. If any cached diff exists, stop
   without unstaging or repairing it, even when it overlaps an approved path.
2. Stage only the exact paths and hunks in the approved candidate, including
   intended untracked or binary files.
3. Run `git write-tree` and require its tree ID to equal
   `approved_candidate_tree`.
4. Inspect the staged diff and path set before running `git commit`.

Create a new commit without `-a`, `--amend`, or `--no-verify`. Do not bypass
hooks. If a hook fails or changes the index or worktree, stop without retrying
or silently repairing state and report the hook output and repository status.

After a successful commit, require `commit^{tree}` to equal both the recorded
index tree and `approved_candidate_tree`. If any tree differs, fail closed and
report the contaminated commit hash. Output an `atomic_commit` artifact
containing the commit hash, subject, committed path set, approved content
digest, and all three verified tree IDs.

For multiple implementation units, repeat implementation, selected tests,
independent review, Architect and Critic validation, and this commit step for
each unit. Never combine unrelated units into one commit.
