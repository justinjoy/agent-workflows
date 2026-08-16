from __future__ import annotations

import json
import re
import subprocess
import sys
import tarfile
import tomllib
import zipfile
from pathlib import Path

from agent_workflows_harness import cli
from agent_workflows_harness.registry import SKILL_BY_ID, SKILLS


ROOT = Path(__file__).resolve().parents[1]
# The prose each selector failure kind uses in the termination contract. Kept
# beside the kinds themselves so a new kind cannot be added without deciding how
# a coordinator is told to end that run.
TERMINATION_PHRASE_BY_KIND = {
    "selector_unavailable": "an unavailable runtime",
    "rule_conflict": "a rule conflict",
    "harness_error": "a harness defect",
}
EXPECTED_ATOMIC_SKILLS = {
    "classify-change-risk",
    "commit-atomic-change",
    "create-implementation-plan",
    "critique-plan",
    "implement-atomic-change",
    "inspect-repository",
    "report-result",
    "review-diff",
    "run-broad-tests",
    "run-focused-tests",
    "validate-final-design",
    "validate-final-risks",
}


def _json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _flat(text: str) -> str:
    """Collapse whitespace so phrase assertions survive a paragraph reflow."""

    return " ".join(text.split())


def test_atomic_skills_exist_in_plugin_layout():
    skill_root = ROOT / "plugins" / "dev-workflows" / "skills"
    actual = {path.parent.name for path in skill_root.glob("*/SKILL.md")}

    assert EXPECTED_ATOMIC_SKILLS <= actual


def test_implementation_skill_resolves_installed_harness_forms():
    skill = _flat(
        (
            ROOT / "plugins" / "dev-workflows" / "skills" / "implementation-skill" / "SKILL.md"
        ).read_text(encoding="utf-8")
    )

    assert "Wirelog-based implementation harness" in skill
    assert "evaluates Wirelog rules through PyreWire" in skill
    assert "<workspace>/.venv/bin/agent-workflows-harness" in skill
    assert "<workspace>/.venv/Scripts/agent-workflows-harness.exe" in skill
    assert "python -m agent_workflows_harness.cli" in skill
    assert "bare command is absent from `PATH`" in skill


def test_implementation_skill_requires_review_consensus_before_commit():
    skill_root = ROOT / "plugins" / "dev-workflows" / "skills"
    implementation = _flat(
        (skill_root / "implementation-skill" / "SKILL.md").read_text(encoding="utf-8")
    )
    commit = _flat(
        (skill_root / "commit-atomic-change" / "SKILL.md").read_text(encoding="utf-8")
    )

    assert (
        "Every code change, including documentation-only and trivial changes"
        in implementation
    )
    assert "Reviewer, Architect, and Critic approve the same candidate" in implementation
    assert "Stage only" in implementation
    assert "approved paths and hunks" in implementation
    assert "without `-a`, `--amend`, or `--no-verify`" in commit
    assert "Require a completely clean real index" in commit
    assert "without unstaging or repairing it" in commit
    assert "approved_candidate_tree" in commit
    assert "require `commit^{tree}` to equal" in commit
    assert "all three verified tree IDs" in commit

    gate_skills = (
        "run-focused-tests",
        "run-broad-tests",
        "review-diff",
        "validate-final-design",
        "validate-final-risks",
    )
    for skill_id in gate_skills:
        contract = _flat((skill_root / skill_id / "SKILL.md").read_text(encoding="utf-8"))
        assert "approved_candidate_tree" in contract

    review = _flat((skill_root / "review-diff" / "SKILL.md").read_text(encoding="utf-8"))
    assert "output must echo" in review
    assert "approved candidate path set" in review
    assert "content digest reviewed" in review


def test_gate_outcomes_must_reach_the_final_report():
    # This is a staleness tripwire, not a semantic gate: it proves the reporting
    # contract still names every gate artifact, not that the prose demands them.
    skill_root = ROOT / "plugins" / "dev-workflows" / "skills"
    report = _flat((skill_root / "report-result" / "SKILL.md").read_text(encoding="utf-8"))
    implementation = _flat(
        (skill_root / "implementation-skill" / "SKILL.md").read_text(encoding="utf-8")
    )

    # Derive the artifact names from the registry so renaming a skill output
    # cannot leave the reporting contract silently stale. The two explicit names
    # guard the skill_id set itself: a typo there would empty the loop silently.
    gate_outputs = {
        SKILL_BY_ID[skill_id].output
        for skill_id in (
            "create-implementation-plan",
            "critique-plan",
            "review-diff",
            "validate-final-design",
            "validate-final-risks",
        )
    }
    assert {"architect_validation", "critic_validation"} <= gate_outputs

    for document in (report, implementation):
        for output in gate_outputs:
            assert output in document
        # `approved_candidate_tree` is a commit-gate term, not a registry output.
        assert "approved_candidate_tree" in document
        assert "blocked skills and their rule reasons" in document
        assert "single-judge mode" in document

    assert "on every termination of the run" in report
    assert "Never end a rejected run silently." in report
    assert "on every termination of the run" in implementation
    assert "omitting its verdict is a silent termination, not a completed run." in (
        implementation
    )

    for skill_id in ("validate-final-design", "validate-final-risks"):
        contract = _flat((skill_root / skill_id / "SKILL.md").read_text(encoding="utf-8"))
        assert "`verdict` of `approved` or `blocked`" in contract
        assert "it never ends the run silently" in contract


def test_every_selector_failure_kind_terminates_through_the_final_report():
    # The idle failure mode is a run that acts and then answers nothing. A
    # selector exit that yields no plan is the cheapest way to reach it, so
    # every such exit must be documented as a termination that still reports.
    skill_root = ROOT / "plugins" / "dev-workflows" / "skills"
    implementation = _flat(
        (skill_root / "implementation-skill" / "SKILL.md").read_text(encoding="utf-8")
    )
    report = _flat((skill_root / "report-result" / "SKILL.md").read_text(encoding="utf-8"))

    # Adding a kind to the CLI without a termination phrase fails here first.
    assert set(TERMINATION_PHRASE_BY_KIND) == set(cli.EXIT_BY_KIND)

    # Scope the phrase to the sentence that actually carries the obligation.
    # A whole-file check passes as soon as the kind is named anywhere -- and it
    # did: `harness_error` reached the exit list while the list of terminations
    # requiring a report still omitted it.
    lists = {}
    for name, document in (("implementation", implementation), ("report", report)):
        found = re.search(
            r"not only after a successful commit\. (.*?) (?:each )?still terminates "
            r"the run",
            document,
        )
        assert found, f"{name} no longer lists the terminations that require a report"
        lists[name] = found.group(1)

    for kind, phrase in TERMINATION_PHRASE_BY_KIND.items():
        assert f"exit `{cli.EXIT_BY_KIND[kind]}`, `{kind}`" in implementation, kind
        for name, termination_list in lists.items():
            assert phrase in termination_list, (name, kind, phrase)

    assert "Report the conflict through `report-result` and stop." in implementation
    assert "Producing no plan is never a reason to stop without responding." in (
        implementation
    )
    for document in (implementation, report):
        assert "`error.kind` and exit code when the run produced no plan" in document


# The delivery clause every dispatched role skill carries, generic across roles.
# Membership in this set is what the workflow's own dispatch sentences are
# cross-checked against.
DELIVERY_CLAUSE = "is a failed dispatch and its work is lost"
# Qualifiers that turn an obligation into advice. Every contract assertion here
# is a substring check, so a hedge in front of a rule leaves the substrings
# matching while the rule stops binding -- demonstrated, not assumed. Shared so
# every test that pins a rule bans them, rather than whichever one remembered.
HEDGES = (
    "where practical",
    "where possible",
    "when convenient",
    "where convenient",
    "prefer",
    "should ordinarily",
    "except where no other assignment",
    "where the host allows",
)
# Which workflow pass owns each dispatch. Keyed by heading text rather than
# heading number, so renumbering the workflow does not break it, and required
# below to equal the set derived from the contract, so it cannot go stale.
DISPATCHING_PASS_BY_SKILL = {
    "create-implementation-plan": "Architect Pass",
    "critique-plan": "Critic Pass",
    "review-diff": "Reviewer Pass",
    "validate-final-design": "Architect and Critic Validation",
    "validate-final-risks": "Architect and Critic Validation",
}
# Host mechanisms that must never reach a shipped contract: the same files go to
# Claude, Codex, Gemini, and Antigravity. Bare "Task" is deliberately absent --
# it would fire on ordinary prose, and a tripwire that cries wolf gets deleted.
HOST_MECHANISM_TOKENS = ("SendMessage", "subagent_type", 'to: "main"')


def _section(document: str, heading: str) -> str:
    """The flattened text of one section, up to the next heading of its level or above.

    Stopping only at the same level makes the last section of its depth swallow
    everything after it, so an assertion scoped to that section would pass on
    text living somewhere else entirely -- the whole-file check this helper
    exists to replace. A deeper heading does not end the section: a subsection
    belongs to its parent.
    """

    level = heading.split(" ", 1)[0]
    at = document.find(heading)
    if at == -1:
        # Return empty rather than raising, so the caller's assertion message
        # about the missing heading is the one that actually fires.
        return ""
    rest = document[at + len(heading) :]
    stops = [
        found
        for depth in range(1, len(level) + 1)
        if (found := rest.find(f"\n{'#' * depth} ")) != -1
    ]
    return _flat(rest[: min(stops)] if stops else rest)


def _roles_declaring_delivery(skill_root) -> set[str]:
    """Registry skills whose own contract carries the delivery clause."""

    return {
        skill_id
        for skill_id in SKILL_BY_ID
        if (skill_root / skill_id / "SKILL.md").is_file()
        and DELIVERY_CLAUSE
        in _flat((skill_root / skill_id / "SKILL.md").read_text(encoding="utf-8"))
    }


def _dispatch_sections(raw: str) -> dict[str, set[str]]:
    """Numbered workflow passes that dispatch, and the roles each one names.

    Keyed by heading, so the positional fact survives: which pass dispatches
    which role. A flat set alone would stop noticing a dispatch sentence that
    drifted out of its own pass, which is what the removed hand-written
    heading map used to catch.
    """

    assert _section(raw, "## Workflow"), "the contract no longer has a Workflow section"

    skill_id_by_output = {skill.output: skill.skill_id for skill in SKILLS}
    sections = {}
    # Numbered `### N.` headings exist only under `## Workflow`. `coordinator
    # holds` also appears in Agent Use, where it names no artifact today;
    # scanning passes rather than the whole file keeps that from poisoning the
    # set if an example is ever added there.
    # The token run stops at the first word that is not a backticked name, so
    # `approved_candidate_tree` in "echoing the ..." is not swallowed and no
    # allowlist is needed -- an allowlist here would be an escape hatch that
    # every future non-artifact token gets appended to.
    for heading in re.findall(r"\n(### \d+\. [^\r\n]+)", raw):
        skills = set()
        for names in re.findall(
            r"coordinator holds ((?:`\w+`)(?:(?:,| and) `\w+`)*)",
            _section(raw, heading),
        ):
            for token in re.findall(r"`(\w+)`", names):
                assert token in skill_id_by_output, f"unknown delivery artifact: {token}"
                skills.add(skill_id_by_output[token])
        if skills:
            sections[heading] = skills
    return sections


def _roles_dispatched_by_the_workflow(raw: str) -> set[str]:
    """Registry skills the workflow dispatches, read off the contract itself."""

    return {
        skill_id
        for skills in _dispatch_sections(raw).values()
        for skill_id in skills
    }


def test_the_workflow_and_the_role_skills_agree_on_who_is_dispatched():
    # Two independently maintained lists used to encode this, so a role could be
    # added to one and missed by the other and nothing failed. Derive both sides
    # and require them equal: rewording a dispatch sentence shrinks one side,
    # adding a role skill clause without a dispatch sentence grows the other,
    # and either fails loudly. Deriving one side FROM the other would instead
    # make the check a tautology that can only shrink in silence.
    #
    # Residual hole, unclosable without a registry field: a new dispatched role
    # with no matching `coordinator holds \`x\`` sentence AND no clause in its
    # own skill is invisible to both. A paraphrased sentence counts as absent
    # here, so the escape needs two independent omissions -- copying a sibling
    # role skill, which is how these get written, grows one side and fails.
    skill_root = ROOT / "plugins" / "dev-workflows" / "skills"
    raw = (skill_root / "implementation-skill" / "SKILL.md").read_text(encoding="utf-8")

    declaring = _roles_declaring_delivery(skill_root)
    dispatched = _roles_dispatched_by_the_workflow(raw)

    assert declaring, "no role skill carries the delivery clause"
    assert dispatched, "the workflow names no dispatched role"
    # Membership alone is circular once both sides are derived, and a count of
    # dispatching passes is too weak -- a sentence moving between two passes
    # that both already dispatch keeps the count. Pin which pass owns which
    # dispatch instead. This map is hand-written, but unlike the two it
    # replaced it cannot drift silently: the assertion below requires it to
    # equal the derived set. Keyed by heading text, not number, so renumbering
    # the workflow does not break it.
    sections = _dispatch_sections(raw)
    assert set(DISPATCHING_PASS_BY_SKILL) == dispatched, (
        f"the recorded dispatching passes {sorted(DISPATCHING_PASS_BY_SKILL)} do not "
        f"match the roles the workflow dispatches {sorted(dispatched)}"
    )
    for skill_id, pass_name in DISPATCHING_PASS_BY_SKILL.items():
        owning = [heading for heading in sections if pass_name in heading]
        assert len(owning) == 1, (
            f"{skill_id} should be dispatched by exactly one {pass_name!r}, "
            f"found {owning} among {sorted(h.strip() for h in sections)}"
        )
        assert skill_id in sections[owning[0]], (skill_id, owning[0].strip())
    assert declaring == dispatched, (
        f"role skills declaring delivery {sorted(declaring)} do not match the roles "
        f"the workflow dispatches {sorted(dispatched)}"
    )


def test_section_slicing_stops_at_the_next_heading_of_the_same_level_or_above():
    document = "## A\nalpha\n### A1\nbeta\n## B\ngamma\n"

    # A subsection belongs to its parent.
    assert _section(document, "## A") == "alpha ### A1 beta"
    # A trailing subsection must not swallow what follows its parent.
    assert _section(document, "### A1") == "beta"
    assert _section(document, "## B") == "gamma"


def test_the_contract_requires_confirmed_delivery_of_every_role_artifact():
    # A role that finishes without its output reaching the coordinator is the
    # dispatch-layer form of the silent termination this contract exists to
    # prevent: the work is done and then lost. This is a staleness tripwire --
    # there is no dispatch runtime to exercise, so it can only prove the
    # contract still states the obligation, not that a coordinator obeys it.
    skill_root = ROOT / "plugins" / "dev-workflows" / "skills"
    raw = (skill_root / "implementation-skill" / "SKILL.md").read_text(encoding="utf-8")
    implementation = _flat(raw)
    report = _flat((skill_root / "report-result" / "SKILL.md").read_text(encoding="utf-8"))

    dispatched = _roles_dispatched_by_the_workflow(raw)
    artifacts = {SKILL_BY_ID[skill_id].output for skill_id in dispatched}
    # Guards the derivation itself: a broken regex would empty every loop below.
    assert {"implementation_plan", "review_findings"} <= artifacts

    agent_use = _section(raw, "## Agent Use and Degraded Mode")
    assert agent_use, "the contract no longer has an Agent Use and Degraded Mode section"

    # Assert inside the sentence carrying each obligation, not anywhere in the
    # file: every artifact name below already appears in the reporting list, so
    # a whole-file membership check would pass on a contract that says nothing.
    assert "Confirm receipt before treating any dispatched pass as complete." in agent_use
    assert (
        "without the coordinator holding its artifact is a failed dispatch, not a "
        "completed pass" in agent_use
    )
    assert "Re-dispatch a failed role at most once, and only when something material" in (
        agent_use
    )
    assert "degrade that role alone and keep every other role independent" in agent_use
    # Degrading a role must name an action. Left undefined, the only reading
    # that is an action is absorbing the role, which is what the pairing rule
    # forbids -- the contract would say do X and not-X in one breath, and an
    # agent would take the convenient branch and self-review.
    assert "Degrading a role means the coordinator runs that skill itself" in agent_use
    assert "must not do that while it already holds the other side" in agent_use
    # The exit that keeps that from being a deadlock.
    assert "stop the run as blocked and report it through `report-result`" in agent_use
    # The substance floor: an artifact that echoes nothing it judged is not
    # evidence, so requiring delivery cannot be satisfied by a rubber stamp.
    assert "echoes the identifiers its skill requires" in agent_use
    # Host-wide unavailability used to keep its own, broader rule: the whole
    # workflow degraded and the coordinator ran every gate. That is retired --
    # a run with no independent agent now stops rather than approving its own
    # work -- so what is pinned here is the replacement, not the old branch.
    assert "no independent agent is available in the host at all" in agent_use
    assert "stop the run as blocked and report it" in agent_use
    # The floor is only as strong as what each role skill mandates, so the
    # contract has to require that every dispatched role mandates something.
    assert "must therefore require at least one such identifier" in agent_use
    # And it must say plainly what these floors are not, or a later reader
    # mistakes them for authentication and builds on that.
    assert "None of these is unforgeable" in agent_use
    assert "not to authenticate the work" in agent_use

    # Each dispatched role skill must actually carry an identifier requirement.
    # Semantic checking is impossible -- the identifier differs per role -- so
    # this pins the per-role floor sentence and nothing stronger.
    floors = {
        "create-implementation-plan": "must name the concrete repository paths",
        "critique-plan": "must name the plan elements it examined",
        "review-diff": "content digest reviewed",
        "validate-final-design": "`approved_candidate_tree` ID being judged",
        "validate-final-risks": "`approved_candidate_tree` ID being judged",
    }
    assert set(floors) == dispatched, "a dispatched role has no recorded substance floor"
    for skill_id, phrase in floors.items():
        contract = _flat((skill_root / skill_id / "SKILL.md").read_text(encoding="utf-8"))
        assert phrase in contract, skill_id

    # Re-asserting that a pass names its own artifact would be circular here --
    # the derivation reads exactly those sentences. The non-circular half, that
    # the sentences stay spread across the passes that own them, is asserted by
    # test_the_workflow_and_the_role_skills_agree_on_who_is_dispatched.

    # Detecting a lost dispatch is worthless if the user is never told, and a
    # report with no producer per artifact reads identically whether the gate
    # ran independently or the coordinator quietly wrote it.
    for document in (implementation, report):
        assert "every role dispatch that delivered no artifact" in document
        assert "which roles ran degraded as a result" in document
        assert "which agent produced each role artifact" in document
        assert "`coordinator, degraded`" in document

    # Portability: the mechanism is one host's, the contract is four hosts'.
    shipped = list((ROOT / "plugins").rglob("SKILL.md"))
    shipped += list((ROOT / "plugins").rglob("agents/*.yaml"))
    assert len(shipped) > len(dispatched), "no shipped contracts found"
    for path in shipped:
        text = path.read_text(encoding="utf-8")
        for token in HOST_MECHANISM_TOKENS:
            assert token not in text, f"{path.name} names a host mechanism: {token}"


def test_every_dispatched_role_skill_states_that_producing_is_not_delivering():
    # Agent Use binds the coordinator, which is the side that did not fail. A
    # dispatched role reads only its own atomic skill, and these skills are also
    # invocable directly, so the clause is conditioned on being dispatched
    # rather than asserting a coordinator always exists.
    #
    # Iterates the roles the workflow says it dispatches, and asserts the
    # artifact-specific wording -- which is stricter than the generic clause the
    # dispatched-set agreement test matches on, so this is not a tautology.
    skill_root = ROOT / "plugins" / "dev-workflows" / "skills"
    raw = (skill_root / "implementation-skill" / "SKILL.md").read_text(encoding="utf-8")

    for skill_id in sorted(_roles_dispatched_by_the_workflow(raw)):
        contract = _flat((skill_root / skill_id / "SKILL.md").read_text(encoding="utf-8"))
        artifact = SKILL_BY_ID[skill_id].output
        assert (
            f"When a coordinator dispatched this skill, producing `{artifact}` is "
            "not delivering it" in contract
        ), skill_id
        assert "is a failed dispatch and its work is lost" in contract, skill_id
        # Without this the clause is wrong under direct invocation, where the
        # caller is the coordinator and there is nothing to return to.
        assert "Under direct invocation the caller is the coordinator" in contract, skill_id


NON_JUDGING_DISPATCHED_ROLES = frozenset(
    # Dispatched, but they return proposals rather than verdicts on the
    # candidate. A new dispatched role must be classified here or the judgment
    # set below changes shape and this test says so.
    {"create-implementation-plan", "critique-plan"}
)


def test_no_agent_judges_an_artifact_it_produced():
    # Stated over the subject of judgment, not over "a candidate". That is what
    # makes plan-author != plan-critic absolute -- critique-plan's subject IS
    # the plan -- while leaving final validation surrenderable, since its
    # subject is the candidate and the critique is only an input. Broader and
    # single-judge mode becomes impossible; narrower and planning falls back to
    # a preference, which is the defect issue #5 was opened on.
    #
    # Staleness tripwire: there is no dispatch runtime here, so this proves the
    # contract states the obligation, never that a coordinator obeys it.
    skill_root = ROOT / "plugins" / "dev-workflows" / "skills"
    raw = (skill_root / "implementation-skill" / "SKILL.md").read_text(encoding="utf-8")
    agent_use = _section(raw, "## Agent Use and Degraded Mode")
    assert agent_use, "the contract no longer has an Agent Use and Degraded Mode section"

    judging = _roles_dispatched_by_the_workflow(raw) - NON_JUDGING_DISPATCHED_ROLES
    assert judging == {"review-diff", "validate-final-design", "validate-final-risks"}, (
        "the set of dispatched passes that judge the candidate changed; classify "
        "the new role in NON_JUDGING_DISPATCHED_ROLES or update this set"
    )
    for skill_id in judging:
        assert f"`{skill_id}`" in agent_use, skill_id

    assert "No agent judges an artifact it produced." in agent_use
    # The half that must stay absolute, named by its own artifact.
    assert "producer of an `implementation_plan` never holds `critique-plan`" in agent_use
    # The generality fix: the rule is about who ends up holding both, not about
    # how they got there.
    assert "by dispatch or by degradation" in agent_use

    # State-form, so the report can be checked against it, and auditable, so
    # "never by choice" is not a claim about a mental state. Without the second
    # clause the obligation reads as a preference and licenses exactly the
    # same-agent-holds-both case this exists to forbid.
    assert "no single agent holds both `validate-final-design` and" in agent_use
    assert "admit no assignment that separates them" in agent_use
    assert "never taken by choice" in agent_use
    assert "name the assignment that could not be constructed" in agent_use
    # Decided up front, or a greedy dispatch order manufactures a true
    # "no assignment exists" and reports the collapse as unavoidable.
    assert "Fix the assignment before the first dispatch" in agent_use

    # The rule must precede the degradation paragraph. Widening the existing
    # coordinator sentence in place satisfies a membership check and fails this.
    assert agent_use.index("No agent judges an artifact it produced.") < agent_use.index(
        "Degrading a role means the coordinator runs that skill itself"
    )

    # Every guarantee single-judge mode gives up, not just the headline one.
    for surrender in (
        "The design verdict and the risk verdict come from one mind.",
        "validates risks against a critique it wrote",
        "Both final validations read review findings it wrote.",
        "independently critiqued but not independently authored",
        "cleared the plan at `critique-plan` before reviewing and validating",
    ):
        assert surrender in agent_use, surrender

    # Everything above is a substring check, so a hedge inserted in front of
    # either rule leaves all of them matching while the rule becomes advice.
    # That was demonstrated, not assumed: prefixing both halves with a
    # qualifier keeps the whole suite green. This does not close the gap -- no
    # substring test can, and these tests never prove a coordinator obeys the
    # contract, only that the contract says it -- but it puts the cost above
    # one adjective.
    for hedge in HEDGES:
        assert hedge not in agent_use.lower(), hedge


def test_the_planning_passes_do_not_contradict_single_judge_mode():
    # One policy written in three places, with the older writings left behind,
    # is the defect this whole issue was opened on. The Agent Use section says
    # the coordinator authors the plan in single-judge mode; the two planning
    # passes and the docs must not still describe the assignment it reverses.
    #
    # Staleness tripwire: proves the three writings agree, not that a
    # coordinator follows any of them.
    skill_root = ROOT / "plugins" / "dev-workflows" / "skills"
    raw = (skill_root / "implementation-skill" / "SKILL.md").read_text(encoding="utf-8")

    architect = _section(raw, "### 3. Architect Pass")
    critic = _section(raw, "### 4. Critic Pass")
    assert architect and critic, "the planning passes were renamed or removed"

    # The Architect Pass still opens by asking for an independent agent, which
    # is right for two or more. It must name the case that reverses it.
    assert "In `single-judge mode` the coordinator writes the plan itself" in architect
    # The Critic Pass must not assume an Architect agent wrote the plan, and
    # must say why it is the pass that stays independent.
    assert "challenge the plan, whoever wrote it" in critic
    assert "never goes to the agent that produced the plan" in critic
    # Pin the imperative, not just the claim. A hedge blacklist cannot enumerate
    # every qualifier -- "where the host allows it" defeats one and reads fine --
    # so weakening `must` here has to break a substring rather than dodge a list.
    assert "it is the one that must stay independent" in critic
    assert "the Architect plan" not in critic, (
        "the Critic Pass still assumes an Architect agent authored the plan"
    )

    # The docs state the same three separations. The first two are absolute and
    # must not be written as preferences beside an absolute rule.
    doc = _flat((ROOT / "docs" / "how-it-works.md").read_text(encoding="utf-8"))
    assert "The plan's author never critiques it" in doc
    assert "The Implementer never reviews or validates its own candidate" in doc
    assert "This is the one of these three a run may lose" in doc
    for stale in (
        "Architect and Critic should be independent",
        "Implementer and Reviewer should be independent",
    ):
        assert stale not in doc, stale

    # Same countermeasure as the rule test next door, for the same reason: the
    # assertions above are substrings, so hedging all three obligations leaves
    # every one of them matching while the policy becomes advice. That is
    # issue #5's defect -- policy stated as preference -- reintroduced with the
    # tripwire green, and it was demonstrated against this test before the ban
    # was added here.
    for hedge in HEDGES:
        assert hedge not in critic.lower(), hedge
        assert hedge not in _flat(_section(raw, "### 3. Architect Pass")).lower(), hedge
    bullets = doc[doc.index("The workflow depends on separation between roles:") :][:1200]
    for hedge in HEDGES:
        assert hedge not in bullets.lower(), hedge


def test_the_contract_establishes_agent_capacity_before_the_first_dispatch():
    # Knowing the count up front is what turns a derivable dead end into a stop
    # before the work exists. Staleness tripwire, as above.
    skill_root = ROOT / "plugins" / "dev-workflows" / "skills"
    raw = (skill_root / "implementation-skill" / "SKILL.md").read_text(encoding="utf-8")
    implementation = _flat(raw)
    report = _flat((skill_root / "report-result" / "SKILL.md").read_text(encoding="utf-8"))
    agent_use = _section(raw, "## Agent Use and Degraded Mode")
    assert agent_use, "the contract no longer has an Agent Use and Degraded Mode section"

    # Bound into the existing pre-dispatch sentence as one string. `before the
    # first dispatch` already occurred on its own before this change, so a bare
    # assertion on it would have been green against the unmodified contract.
    assert (
        "Identify how a dispatched role's output actually reaches the coordinator, "
        "and how many independent agents the host can provide, before the first "
        "dispatch" in agent_use
    )
    # The rule has to read before the number, or the number can be edited and
    # stay internally consistent with a contract that no longer means it.
    requirement = "one independent agent to hold the judgment gates the selected plan requires"
    assert requirement in agent_use
    assert agent_use.index(requirement) < agent_use.index("one and two respectively")
    # The fail-closed path selects every gate, so it is the strictest case here,
    # not an exemption from it.
    assert "the fail-closed non-trivial plan when the runtime could not run" in agent_use
    assert "stop the run as blocked before editing" in agent_use

    # A capacity stop yields no gate verdict, so report-result's closing
    # paragraph -- conditioned on one -- never catches it. It has to be a listed
    # termination and a named report item, in both documents or it ships in one.
    for name, document in (("implementation", implementation), ("report", report)):
        listed = re.search(
            r"not only after a successful commit\. (.*?) (?:each )?still terminates the run",
            document,
        )
        assert listed, f"{name} no longer lists the terminations that require a report"
        assert "no independent agent to hold the judgment gates" in listed.group(1), name
        assert (
            "the independent-agent count the host offered and the judgment gates it "
            "could not place" in document
        ), name

    doc = _flat((ROOT / "docs" / "how-it-works.md").read_text(encoding="utf-8"))
    assert "how many independent agents the host can provide, before the first dispatch" in doc
    # Accurate cost: such a host still runs and still reports. It cannot commit.
    assert "can no longer reach a commit through this harness" in doc


def test_whole_workflow_degradation_is_retired_from_every_shipped_contract():
    # The coordinator running every gate on its own change produced approvals
    # nobody independent had given. Retiring it is only real if no shipped
    # contract still offers it, so this sweeps them all rather than the one
    # file the retirement edited.
    #
    # docs/how-it-works.md is deliberately NOT swept: it is the file whose job
    # is to explain what changed and why, and banning the phrase there would
    # make documenting the retirement a test failure.
    shipped = [*(ROOT / "plugins").rglob("SKILL.md"), *(ROOT / "plugins").rglob("agents/*.yaml")]
    assert len(shipped) > 5, "no shipped contracts found"
    for path in shipped:
        text = _flat(path.read_text(encoding="utf-8"))
        assert "degraded sequential mode" not in text, path.name
        assert "except under whole-workflow" not in text, path.name

    # Paired with the positive for the state that replaced it: a negative alone
    # goes stale in silence if the mode is reworded rather than removed.
    skill_root = ROOT / "plugins" / "dev-workflows" / "skills"
    for name in ("implementation-skill", "report-result"):
        document = _flat((skill_root / name / "SKILL.md").read_text(encoding="utf-8"))
        assert "single-judge mode" in document, name


def test_the_contract_never_promises_a_document_for_rejected_input():
    # exit 2 comes from argparse and prints nothing on stdout. Listing it under
    # a sentence that promised an `error` document told coordinators to parse a
    # document that is never there -- the same "empty stdout reads as no plan"
    # hazard the rest of this contract exists to close.
    skill_root = ROOT / "plugins" / "dev-workflows" / "skills"
    implementation = _flat(
        (skill_root / "implementation-skill" / "SKILL.md").read_text(encoding="utf-8")
    )
    doc = _flat((ROOT / "docs" / "how-it-works.md").read_text(encoding="utf-8"))

    assert "Stdout is empty and the cause is on stderr" in implementation

    # Derive the document-emitting exits from the kind table rather than
    # listing them, so adding a kind cannot leave this sentence stale.
    sentence = re.search(
        r"Exits ([^.]*?) emit an `error` document carrying a `kind` on stdout; "
        r"exit `2` does not\.",
        implementation,
    )
    assert sentence, "the contract no longer says which exits carry a document"
    for code in sorted(cli.EXIT_BY_KIND.values()):
        assert f"`{code}`" in sentence.group(1), code

    assert "Exit `2` prints no document at all" in doc
    # The durable-trace claim must not cover the exit that cannot reach the log.
    trace = re.search(r"A run that failed at exit ([^.]*?) appends an", doc)
    assert trace, "the docs no longer scope the durable-trace claim"
    for code in sorted(cli.EXIT_BY_KIND.values()):
        assert f"`{code}`" in trace.group(1), code


def test_provider_versions_follow_release_policy():
    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    expected_version = project["project"]["version"]
    assert expected_version == "2.1.0"

    provider_plugin_manifests = [
        ROOT / "plugins" / "dev-workflows" / f".{host}-plugin" / "plugin.json"
        for host in ("antigravity", "claude", "codex", "gemini")
    ]
    coupled_marketplace_manifests = [
        ROOT / f".{host}-plugin" / "marketplace.json"
        for host in ("antigravity", "gemini")
    ]

    assert all(
        _json(path)["version"] == expected_version
        for path in provider_plugin_manifests
    )
    assert all(
        _json(path)["plugins"][0]["version"] == expected_version
        for path in coupled_marketplace_manifests
    )

    claude_entry = _json(ROOT / ".claude-plugin" / "marketplace.json")["plugins"][0]
    assert "version" not in claude_entry


def test_claude_marketplace_points_to_shared_lifecycle_skill_layout():
    marketplace = _json(ROOT / ".claude-plugin" / "marketplace.json")
    entry = marketplace["plugins"][0]
    plugin_root = (ROOT / entry["source"]).resolve()

    assert entry["source"] == "./plugins/dev-workflows"
    assert plugin_root.is_relative_to(ROOT.resolve())
    assert "strict" not in entry
    assert "version" not in entry
    assert {"review", "wirelog", "atomic-commit"} <= set(entry["tags"])

    manifest = _json(plugin_root / ".claude-plugin" / "plugin.json")
    implementation_path = plugin_root / "skills" / "implementation-skill" / "SKILL.md"
    commit_path = plugin_root / "skills" / "commit-atomic-change" / "SKILL.md"

    assert manifest["name"] == entry["name"] == "dev-workflows"
    for description in (manifest["description"], entry["description"]):
        assert "mandatory review" in description
        assert "Architect/Critic approval" in description
        assert "verified atomic commits" in description
    assert implementation_path.is_file()
    assert commit_path.is_file()

    implementation = _flat(implementation_path.read_text(encoding="utf-8"))
    commit = _flat(commit_path.read_text(encoding="utf-8"))
    assert "including documentation-only and trivial changes" in implementation
    assert "commit-atomic-change" in implementation
    assert "Reviewer, Architect, and Critic approve" in implementation
    assert "approved_candidate_tree" in commit


def test_antigravity_plugin_root_exposes_shared_lifecycle_skills():
    plugin_root = ROOT / "plugins" / "dev-workflows"
    manifest = _json(plugin_root / "plugin.json")

    assert set(manifest) == {"$schema", "name", "description"}
    assert manifest["$schema"] == "https://antigravity.google/schemas/v1/plugin.json"
    assert manifest["name"] == "dev-workflows"
    assert "mandatory review" in manifest["description"]
    assert "Architect/Critic approval" in manifest["description"]
    assert "verified atomic commits" in manifest["description"]

    skill_root = plugin_root / "skills"
    implementation = _flat(
        (skill_root / "implementation-skill" / "SKILL.md").read_text(encoding="utf-8")
    )
    commit = _flat(
        (skill_root / "commit-atomic-change" / "SKILL.md").read_text(encoding="utf-8")
    )
    prompt = (
        skill_root / "implementation-skill" / "agents" / "antigravity.yaml"
    ).read_text(encoding="utf-8")

    assert "including documentation-only and trivial changes" in implementation
    assert "Reviewer, Architect, and Critic approve" in implementation
    assert "approved_candidate_tree" in commit
    assert "/dev-workflows:implementation-skill" in prompt
    assert "independent review" in prompt
    assert "Architect/Critic approval" in prompt
    assert "verified atomic commit" in prompt


def test_package_metadata_uses_wirelog_terminology():
    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    module_docstring = (
        ROOT / "src" / "agent_workflows_harness" / "__init__.py"
    ).read_text(encoding="utf-8")

    assert "Wirelog-based" in project["project"]["description"]
    assert "Wirelog-based" in module_docstring
    assert "Datalog" not in project["project"]["description"]
    assert "Datalog" not in module_docstring


def test_source_distribution_manifest_includes_plugin_assets():
    manifest = (ROOT / "MANIFEST.in").read_text(encoding="utf-8")

    assert "recursive-include plugins" in manifest
    assert "recursive-include docs" in manifest
    assert "include .agents/plugins/marketplace.json" in manifest
    assert "include .antigravity-plugin/marketplace.json" in manifest
    assert "include .claude-plugin/marketplace.json" in manifest
    assert "include .gemini-plugin/marketplace.json" in manifest


def test_built_artifacts_match_runtime_and_plugin_distribution_contract(tmp_path):
    subprocess.run(
        [
            sys.executable,
            "-m",
            "build",
            "--no-isolation",
            "--outdir",
            str(tmp_path),
            str(ROOT),
        ],
        check=True,
        text=True,
        capture_output=True,
    )

    sdist = next(tmp_path.glob("agent_workflows-*.tar.gz"))
    wheel = next(tmp_path.glob("agent_workflows-*.whl"))

    with tarfile.open(sdist, "r:gz") as archive:
        sdist_members = set(archive.getnames())
    required_suffixes = {
        ".agents/plugins/marketplace.json",
        ".antigravity-plugin/marketplace.json",
        ".claude-plugin/marketplace.json",
        ".gemini-plugin/marketplace.json",
        "plugins/dev-workflows/plugin.json",
        "plugins/dev-workflows/skills/report-result/SKILL.md",
        "plugins/dev-workflows/skills/commit-atomic-change/SKILL.md",
    }
    assert all(
        any(member.endswith(suffix) for member in sdist_members)
        for suffix in required_suffixes
    )

    with zipfile.ZipFile(wheel) as archive:
        wheel_members = set(archive.namelist())
    assert "agent_workflows_harness/cli.py" in wheel_members
    assert "agent_workflows_harness/selector.py" in wheel_members
    assert any(name.endswith(".dist-info/entry_points.txt") for name in wheel_members)
    assert not any(name.startswith("plugins/") for name in wheel_members)
