# How It Works

## Implementation Skill

`implementation-skill` is a Wirelog-based harness for code changes, evaluated
through PyreWire. It turns one implementation request into request facts,
evaluates those facts with explicit Wirelog rules, and returns a
machine-readable plan of atomic skills to run.

Use it when the agent should not freely choose its own workflow. The harness
makes the selection explicit: trivial and documentation-only changes can skip
planning and broad tests, but every change still selects independent review,
final Architect and Critic validation, and an atomic commit. Non-trivial,
cross-module, shared-behavior, or external-service changes also select planning,
critique, and broad validation.

## Wirelog Harness

The runtime package exposes:

```bash
agent-workflows-harness "refactor auth workflow and add tests"
```

The command emits JSON:

```json
{
  "request": {
    "request_id": "req",
    "request_type": "code_change",
    "properties": ["needs_tests", "non_trivial", "touches_shared_behavior"]
  },
  "selected": [
    {
      "order": 10,
      "skill_id": "inspect-repository",
      "reason": "code_change_requires_repository_context"
    }
  ],
  "blocked": []
}
```

Selection is computed by Wirelog rules through PyreWire, not by natural-language
skill descriptions.

The harness accepts only its documented request properties and the
`code_change` request type before generating Wirelog source. Unknown or malformed
facts fail with an input error. If a request contains both `trivial` and concrete
risk evidence such as `non_trivial`, shared behavior, external services, or
multi-file scope, the risk evidence wins and the trivial hint is removed.

Documentation-only requests select `implement-atomic-change`, a
documentation-specific focused-validation reason, independent review, final
Architect and Critic validation, and `commit-atomic-change`. They skip planning
and broad tests only when no separate risk fact requires those gates. Multi-file
or explicitly non-trivial documentation may still select the larger workflow, while
`docs_only` combined with external-service or shared-behavior impact is rejected
as contradictory input. Requests with no risk or documentation facts fail
closed to `non_trivial`.

When the selector cannot run at all, the command emits an error document on
stdout instead of a plan, keeps the human-readable cause on stderr, and uses
exit `3`:

```json
{
  "error": {
    "kind": "selector_unavailable",
    "message": "PyreWire/Wirelog runtime unavailable. Ensure pyrewire is installed and WIRELOG_LIB points to libwirelog.",
    "cause": "No module named 'pyrewire'"
  }
}
```

In `--text` mode the same failure prints one line instead:

```
error: selector_unavailable # No module named 'pyrewire'
```

Two Wirelog rules that disagree about the same skill are the other way a run
produces no plan. A plan must be a deterministic function of the request facts,
so the harness fails closed at exit `4` rather than keeping whichever row the
relation happened to yield last. The remedy is to fix the rules, not the
environment, so it is never reported as an unavailable runtime:

```json
{
  "error": {
    "kind": "rule_conflict",
    "message": "Wirelog rules disagree about the same skill. The plan is not a deterministic function of the request facts; fix the rules.",
    "cause": "selected rules disagree about the same skill: run-focused-tests: (60, 6), (60, 12)"
  }
}
```

Any other harness defect reaching the caller uses exit `5`. The kind tables are
keyed by kind, so they cannot notice a `HarnessError` subclass added without an
entry in `KIND_BY_EXCEPTION`; such a subclass would otherwise arrive as
`selector_unavailable` and send an operator to check `WIRELOG_LIB` for a bug in
the harness. Exit `5` is what an unclassified harness failure gets instead:

```json
{
  "error": {
    "kind": "harness_error",
    "message": "The harness failed before producing a plan. This is a defect in the harness itself, not in the request or the environment.",
    "cause": "SelectorTimeoutError: rule evaluation exceeded its deadline"
  }
}
```

An error document deliberately carries no `selected` key, so a caller that
reads `payload["selected"]` fails loudly instead of treating a failure as an
empty plan. A caller that defaults the key instead, such as
`payload.get("selected", [])`, defeats that and must branch on the exit code or
on `error.kind`. Exits `3` and `4` are both distinct from argparse's
usage-error `2`, which still signals rejected input. Exit `2` prints no document
at all: argparse reports the cause on stderr, so a caller that parses only
stdout must branch on the exit code to see it.

Exit `0` no longer implies a plan. `--print-ontology` is a successful run that
prints the active TBox and selects nothing, so a caller branches on the query it
asked for as well as on the exit code. That document carries no `selected` key
either, so `payload["selected"]` still fails loudly while
`payload.get("selected", [])` still reads it as an empty plan.

Use `--decision-log path/to/decisions.jsonl` to append the request facts,
selected skills, blocked skills, and rule reasons as durable JSON Lines records.
A run that failed at exit `3`, `4`, or `5` appends an
`agent_workflow.skill_plan_failed` record instead, so a failed selection still
leaves a durable trace. Input
rejected at exit `2` is reported by argparse before the log is reachable and
leaves no record, so an absent record is not evidence that no run was attempted.
A `--print-ontology` run selects nothing, so it has neither record to append; it
warns on stderr rather than letting a caller who supplied `--decision-log`
believe a trace was written.

The log is a trace, not the answer. An unwritable log path warns on stderr and
changes neither the exit code nor the document already written to stdout.

The compatibility `implementation-skill` entrypoint remains stable for plugin
hosts. A host first checks `PATH`, then an executable harness in the current
workspace's `.venv`, then an active Python environment that can import the
harness module. It tries each available form without installing dependencies or
rewriting the host environment. Only when none can run does the skill fail
closed by using the non-trivial plan manually and reporting that the runtime
selector could not execute. See [Harness command resolution](installation.md#harness-command-resolution)
for the exact platform-specific commands.

The Python runtime depends on `pyrewire>=1.0.4,<2.0`. Runtime-backed tests are
required and fail when PyreWire or its native Wirelog library cannot load; a
load failure is not treated as a skipped optional integration.

## Ontology Fact Source

The text classifier recognizes risk by matching keywords. That fails whenever a
request describes a risky surface without using the expected word:

```
"refactor auth workflow and add tests"
  -> touches_shared_behavior  -> broad tests selected

"small one-line change to the login session expiry"
  -> trivial                  -> planning, critique, and broad tests blocked
```

Both requests change authentication behavior. Only the first says so in words
the regex table happens to contain.

The ontology fact source removes that dependence on phrasing. A request may be
stated as ABox triples over a declared TBox:

```bash
agent-workflows-harness --touches session_module --scope one_line
```

`session_module` is declared as an `AuthSurface`, and `AuthSurface ⊑
SharedBehavior ⊑ Surface`. Wirelog computes the transitive closure, so
`touches_shared_behavior` is derived even though the individual carries no
keyword. The same three gates the keyword path dropped are selected again.

Derived properties are reported with the chain that produced them:

```json
"derived": [
  {
    "property": "touches_shared_behavior",
    "from": "touches(req, session_module)",
    "path": "session_module -> AuthSurface -> SharedBehavior"
  }
]
```

Documentation-only status is inferred rather than asserted: a request is
`docs_only` when every surface it touches is a `DocSurface`. Touching a
`readme` alongside an `auth_module` does not qualify.

The selector remains deterministic and does not call an LLM. An LLM may propose
the triples that reach the CLI, but every property is derived from declared
classes and the closure over them. Ontology-derived properties merge with
`--property` values and text classification, and existing invariants still
apply: concrete risk evidence overrides a `trivial` hint, and `docs_only`
combined with code impact is rejected as contradictory input.

Supply a different TBox with `--ontology path/to/tbox.json`. Teaching the
harness that `billing_ledger` is a persistence surface is one entry in
`surface_class`, not an edit to the classifier. The document is validated on
load: terms must be well formed, classes must be declared, `sub_class_of` must
be acyclic, and mapped properties must be ones the selector supports.

The vocabulary a request may draw on is itself observable. `--print-ontology`
prints the active TBox and exits `0` without selecting a plan:

```bash
agent-workflows-harness --print-ontology
```

The document is the same shape `--ontology` reads, so the same command also
answers what a supplied file loaded as after validation, which is otherwise
unobservable:

```json
{
  "property_of_class": [["SharedBehavior", "touches_shared_behavior"]],
  "scope_property": [["one_line", "trivial"]],
  "skill_class": [["review-diff", "ReviewSkill"]],
  "sub_class_of": [["AuthSurface", "SharedBehavior"]],
  "surface_class": [["session_module", "AuthSurface"]]
}
```

That example is a subset: the bundled TBox has more rows in every relation.
Every argument other than `--ontology` is ignored, including `--touches` and
`--scope` values that would otherwise be rejected -- the caller reaching for
this flag is usually the one whose name was just refused. An `--ontology` file
that fails validation still exits `2` and prints nothing, because a document
that did not load cannot be printed.

`--text` prints the same TBox one row per line, in the same relation order:

```
property_of_class: SharedBehavior -> touches_shared_behavior
scope_property: one_line -> trivial
sub_class_of: AuthSurface -> SharedBehavior
surface_class: session_module -> AuthSurface
```

No declared term can contain a space, a colon, or `>`, so the line splits
unambiguously -- but that form is for reading and grepping. JSON is the surface
to parse, and it is the one that round-trips back through `--ontology`.

The bundled ontology also classifies every registered skill (`ReviewSkill`,
`TestSkill`, and so on under `ValidationSkill`). The selector rules do not use
that hierarchy yet; it is declared so rule consolidation can be verified
against the current per-skill rules before replacing them.

## Atomic Skills

The implementation harness can select these smaller skills:

- `inspect-repository`
- `classify-change-risk`
- `create-implementation-plan`
- `critique-plan`
- `implement-atomic-change`
- `run-focused-tests`
- `run-broad-tests`
- `review-diff`
- `validate-final-design`
- `validate-final-risks`
- `commit-atomic-change`
- `report-result`

## Persona Communication

![Implementation Skill persona communication diagram](assets/implementation-skill-communication.svg)

The Coordinator is the communication hub. It gathers repository context, runs
the selected atomic skills, sends each persona only the artifact needed for that
role, resolves disagreements, and keeps unrelated work out of scope.

The personas communicate through raw artifacts rather than shared assumptions:

- Architect returns a plan.
- Critic returns objections.
- Implementer returns an uncommitted atomic candidate and validation output.
- Reviewer returns findings against the raw diff.
- Architect and Critic approve the same immutable candidate against the goal.
- Committer verifies and commits only the approved tree.

## Roles

- **Architect** defines the intended behavior, affected files, interfaces, risks, tests, and atomic commit breakdown.
- **Critic** challenges the plan before code changes begin. It looks for hidden coupling, weak assumptions, over-broad scope, and tests that would not prove the behavior.
- **Implementer** produces an uncommitted candidate in reviewable units and validates each unit.
- **Reviewer** reviews the raw diff for bugs, regressions, missing tests, and scope creep.

The coordinating agent sequences those passes, resolves disagreements, and reports the result. It should not replace the role passes with its own unchecked judgment.

## Independence

The workflow depends on separation between roles:

- The plan's author never critiques it, so the critique is not a confirmation of the plan. This one never bends.
- The Implementer never reviews or validates its own candidate, which is why a host with no independent agent cannot reach a commit. This one never bends either.
- Design and risk validation are argued by different agents wherever an assignment allows it. This is the one of these three a run may lose, and only where no assignment preserves it -- in `single-judge mode` it is lost at final validation, and the report says so. Other separations can still weaken through a degraded role, and the report names those too.

Independence is only real if the role's output arrives. A dispatched role can
finish its work and still deliver nothing, because hosts differ in how a
subagent's output reaches its coordinator: some return it directly, some expect
the role to send it back explicitly, and some expect an agreed file. The
coordinator determines which applies, and how many independent agents the host
can provide, before the first dispatch; names the return path in every dispatch
prompt; and confirms it holds the named artifact before treating the pass as
complete. A role that finished or went idle without delivering is
treated as a failed dispatch, not a completed pass.

The skill deliberately describes this as an obligation rather than naming a
mechanism, because the same contract ships to four hosts. Concrete mechanisms
belong here, not in the skill.

No agent judges an artifact it produced. That is why the producer of a plan
never critiques it, and why the coordinator -- which is the Implementer --
never holds `review-diff`, `validate-final-design`, or `validate-final-risks`.
The rule binds whoever comes to hold both, by dispatch or by degradation, and
it is not a property of the degradation path: a coordinator that dispatched
both planning passes to the same agent has broken it without degrading
anything.

A failed dispatch is re-tried at most once, and only when something material
changes -- resending an identical prompt carries no new information. If that
also delivers nothing, only that role degrades. A judgment gate has nowhere to
degrade to, so one that cannot reach an independent agent stops the run as
blocked instead. With no independent agent at all, every judgment gate would
fall to the author of the change, so the run stops as blocked before editing
rather than approving its own work.

With exactly one independent agent the run continues in single-judge mode: that
agent holds every judgment gate, so it judges both design and risk at final
validation. Planning still separates, with the coordinator authoring the plan
and the agent critiquing it, because the critique is the only pass that ever
interrogates the plan's quality. The mode surrenders five guarantees and the
report names all five -- one mind behind both verdicts, risks validated against
a critique it wrote, both validations reading review findings it wrote, a design
that was independently critiqued but not independently authored, and a reviewer
that had already cleared the plan it reviews against.

The consequence worth stating plainly: a host that can dispatch no independent
agent can no longer reach a commit through this harness. It still runs, and it
still reports -- as a blocked stop naming the count it could offer. That is
deliberate. One agent writing, reviewing and approving its own change satisfied
the gates only nominally, and a report of three approvals from one mind is the
assurance-that-isn't-there this workflow exists to refuse.

The final report must name every dispatch that delivered nothing, every role
that ran degraded, and which independence guarantees were weakened.

## Atomic Changes and Commits

Implementation is split into commit-sized candidates. Each candidate has one
behavioral purpose, touches only the files needed for that purpose, and remains
uncommitted while tests, independent review, and final Architect and Critic
validation run. Blocking findings loop back through implementation, testing,
and review.

After all three roles approve the same candidate digest, the commit skill stages
only its approved paths and hunks, verifies the staged tree, creates a new commit
without bypassing hooks or amending history, and verifies the commit tree still
matches the approved tree. Multiple candidates repeat this lifecycle and produce
one commit each.

This keeps review focused and makes it easier to identify where a regression entered.

## When to Use It

Use `implementation-skill` for:

- behavior changes with multiple affected files
- risky refactors or migrations
- fixes where the failure mode is not obvious
- changes that need explicit test strategy
- PR feedback that requires implementation and review

For small edits, the Wirelog selector produces the small plan: inspection, risk
classification, atomic candidate implementation, focused tests, independent
review, final Architect and Critic validation, atomic commit, and reporting.

## Close Open Issues Goal

Explicitly invoke `$dev-workflows:close-open-issues-goal` or `/dev-workflows:close-open-issues-goal` (the host-specific form) only when you want to create, set, or start the persistent goal for reducing the current repository's open issue count to zero. Invocation creates the goal only: that same turn must not inspect or prioritize issues, implement work, close issues, or create issues unless those actions are separately requested.

When the goal is later executed, begin with the highest-priority open issue and resolve it using `$dev-workflows:implementation-skill` or `/dev-workflows:implementation-skill`. Work discovered while resolving an issue becomes a follow-up issue only after Architect and Critic have assessed it.

Each follow-up issue records:

- scope and intended outcome;
- discovery context or reproducible steps;
- acceptance criteria;
- priority rationale and dependencies, when known.

The goal has no default token budget; one is supplied only when explicitly requested. If another goal is already active, report that constraint and ask the user how to proceed. Do not replace, complete, or block the existing goal merely to create this one.
