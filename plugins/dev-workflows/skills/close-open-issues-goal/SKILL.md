---
name: close-open-issues-goal
description: Set a persistent session goal for reducing a repository's open issue count to zero with priority-first resolution and self-contained follow-up issues. Use when the user explicitly asks to create, set, or start this open-issues resolution goal; do not use to begin resolving issues without an explicit goal-creation request.
---

# Close Open Issues Goal

Invocation is the request: set the goal in the same turn, and set only the goal. Do not inspect, prioritize, implement, close, or create repository issues in that turn unless the user separately asks to begin execution.

## Workflow

1. Take the invocation as the user's own words asking for this goal. Do not stop to confirm that they want it, and do not treat the goal as set until the host confirms it.
2. Use this condition, adapting only the repository identifier when the user supplied one:

   ```text
   Reduce the current repository's open issue count to zero, met when a fresh open-issue listing in this conversation shows none. Select the highest-priority open issue first and resolve it using /dev-workflows:implementation-skill (or $dev-workflows:implementation-skill). When new work is discovered, have Architect and Critic discuss it, then register a self-contained follow-up issue containing scope, reproduction or discovery context, and acceptance criteria.
   ```

3. Set it through the host's own goal mechanism:

   - Claude Code: call `ProposeGoal` with that text as `condition` and `ask_user` false, which sets the goal directly. This invocation is the explicit request that permits `ask_user` false; nothing else in the turn does.
   - A host with no goal mechanism: state the condition as the session's standing objective and carry it across turns yourself.

4. Keep the condition inside the host's limit -- Claude Code caps it at 500 characters -- and keep its end state checkable from the conversation alone, because the evaluator reads the transcript and cannot run commands or read files. If a long repository identifier pushes the text over the cap, shorten the wording rather than dropping the end state or the per-issue workflow.
5. Do not set `token_budget` unless the user explicitly provides one.
6. If a goal is already active, a new one replaces it, so pass `ask_user` true instead and let the replacement be the user's keypress. Do not clear, complete, or block the existing goal yourself.
7. If the goal mechanism is absent from the session, or the host refuses it -- an agent context, a non-interactive session, plan mode still active, restricted hooks -- report the reason in one line and hand the user the exact `/goal <condition>` line to paste, with the condition already filled in.
8. Report the condition that is now active in one or two lines.

## Follow-up Issue Requirements

When this goal is later executed, create a follow-up issue only after Architect and Critic have assessed the newly discovered work. Require every follow-up issue to state:

- scope and intended outcome;
- discovery context or reproducible steps;
- acceptance criteria;
- priority rationale and dependencies, when known.
