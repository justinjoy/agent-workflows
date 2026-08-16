---
name: review-diff
description: Atomic implementation skill that reviews the raw diff for bugs, regressions, missing tests, and scope creep.
---

# Review Diff

Independently review the raw, uncommitted `code_diff` artifact, including its
untracked and binary files. Review the exact candidate content identified by
its base tree, path set, digest, and `approved_candidate_tree` ID.

Output `review_findings` ordered by severity. Findings should cite concrete
files and lines when possible and focus on bugs, regressions, missing tests,
and maintainability risks. The output must echo the `approved_candidate_tree`
ID, approved candidate path set, and content digest reviewed.

For documentation, also verify technical accuracy, commands, internal links,
and consistency with the actual selector output. Any candidate change
invalidates the review and requires a new independent review.

When a coordinator dispatched this skill, producing `review_findings` is not
delivering it: return it the way that dispatch named. A pass that ends without
the coordinator holding it is a failed dispatch and its work is lost. Under
direct invocation the caller is the coordinator and delivery is immediate.
