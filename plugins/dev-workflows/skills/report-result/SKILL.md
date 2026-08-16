---
name: report-result
description: Atomic implementation skill that reports selected skills, validation, commits, and residual risks at the end of a harness run.
---

# Report Result

Produce the final response for the implementation run.

Run this skill on every termination of the run, not only after a successful
commit. A gate rejection, a host that can provide no independent agent to hold
the judgment gates, a blocked commit, an unavailable runtime, a rule conflict, a
harness defect, or an abandoned unit each still terminates the run and still
requires this report. A run must never end without one.

Report:

- selected skill plan, plus blocked skills and their rule reasons, or the
  selector `error.kind` and exit code when the run produced no plan
- `implementation_plan` summary and `critique_findings` when those skills were
  selected
- `review_findings`
- `architect_validation` and `critic_validation`, each with its explicit
  `verdict` and the `approved_candidate_tree` ID it judged
- validation commands and results
- every atomic commit hash, subject, committed path set, and approved tree or
  diff digest
- pull request URL when applicable
- which agent produced each role artifact, or `coordinator, degraded` when the
  coordinator produced it, so a pass that never ran independently cannot be
  reported as one that did
- every role dispatch that delivered no artifact, what changed on any
  re-dispatch, and which roles ran degraded as a result
- when the run stopped before its first dispatch, the independent-agent count
  the host offered and the judgment gates it could not place
- whether the run ran in `single-judge mode`, and every independence guarantee
  that weakened
- residual risks or unavailable validation
- unrelated untracked or modified files

When any gate returned a blocking verdict, report that verdict, its reasons, and
the state the run stopped in. Never end a rejected run silently.
