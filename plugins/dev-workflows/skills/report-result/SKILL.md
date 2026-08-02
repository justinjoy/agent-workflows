---
name: report-result
description: Atomic implementation skill that reports selected skills, validation, commits, and residual risks at the end of a harness run.
---

# Report Result

Produce the final response for the implementation run.

Report:

- selected skill plan
- validation commands and results
- every atomic commit hash, subject, committed path set, and approved tree or
  diff digest
- pull request URL when applicable
- residual risks or unavailable validation
- unrelated untracked or modified files
