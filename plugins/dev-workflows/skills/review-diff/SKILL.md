---
name: review-diff
description: Atomic implementation skill that reviews the raw diff for bugs, regressions, missing tests, and scope creep.
---

# Review Diff

Review the raw `code_diff` artifact.

Output `review_findings` ordered by severity. Findings should cite concrete
files and lines when possible and focus on bugs, regressions, missing tests,
and maintainability risks.
