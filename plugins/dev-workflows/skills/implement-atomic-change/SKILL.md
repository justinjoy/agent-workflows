---
name: implement-atomic-change
description: Atomic implementation skill that edits the codebase in one reviewable implementation unit.
---

# Implement Atomic Change

Apply one coherent implementation unit as an uncommitted atomic commit
candidate. Do not create or amend a Git commit in this skill; committing belongs
to `commit-atomic-change` after review and final validation.

The unit should:

- have one behavioral purpose
- edit only the files required for that purpose
- preserve unrelated user work
- include intended untracked and binary files in the candidate artifact
- use a temporary index derived from the base tree to produce an immutable
  candidate tree without changing the real index
- produce a reviewable `code_diff` artifact with the base tree ID, candidate
  path set, content digest, and `approved_candidate_tree` ID

If a later fix changes the candidate, invalidate its prior validation, review,
and approval artifacts and run those gates again.
