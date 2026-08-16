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
from agent_workflows_harness.registry import SKILL_BY_ID


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
    skill = (
        ROOT / "plugins" / "dev-workflows" / "skills" / "implementation-skill" / "SKILL.md"
    ).read_text(encoding="utf-8")

    assert "Wirelog-based implementation harness" in skill
    assert "evaluates Wirelog rules through PyreWire" in skill
    assert "<workspace>/.venv/bin/agent-workflows-harness" in skill
    assert "<workspace>/.venv/Scripts/agent-workflows-harness.exe" in skill
    assert "python -m agent_workflows_harness.cli" in skill
    assert "bare command is absent from `PATH`" in skill


def test_implementation_skill_requires_review_consensus_before_commit():
    skill_root = ROOT / "plugins" / "dev-workflows" / "skills"
    implementation = (skill_root / "implementation-skill" / "SKILL.md").read_text(
        encoding="utf-8"
    )
    commit = (skill_root / "commit-atomic-change" / "SKILL.md").read_text(
        encoding="utf-8"
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
        contract = (skill_root / skill_id / "SKILL.md").read_text(encoding="utf-8")
        assert "approved_candidate_tree" in contract

    review = (skill_root / "review-diff" / "SKILL.md").read_text(encoding="utf-8")
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
        assert "degraded sequential mode" in document

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


DISPATCHED_ROLE_SKILLS = (
    "create-implementation-plan",
    "critique-plan",
    "review-diff",
    "validate-final-design",
    "validate-final-risks",
)
# Which workflow section dispatches each role. A pass that names no artifact
# cannot be checked for delivery, so the binding is asserted section by section.
DISPATCH_SECTION_BY_SKILL = {
    "create-implementation-plan": "### 3. Architect Pass",
    "critique-plan": "### 4. Critic Pass",
    "review-diff": "### 7. Reviewer Pass",
    "validate-final-design": "### 8. Architect and Critic Validation",
    "validate-final-risks": "### 8. Architect and Critic Validation",
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
    start = document.index(heading) + len(heading)
    rest = document[start:]
    stops = [
        found
        for depth in range(1, len(level) + 1)
        if (found := rest.find(f"\n{'#' * depth} ")) != -1
    ]
    return _flat(rest[: min(stops)] if stops else rest)


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

    artifacts = {SKILL_BY_ID[skill_id].output for skill_id in DISPATCHED_ROLE_SKILLS}
    # Guards the skill-ID tuple itself: a typo there would empty every loop.
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
    assert "no single agent may hold both sides of a gate pair" in agent_use
    # The substance floor: an artifact that echoes nothing it judged is not
    # evidence, so requiring delivery cannot be satisfied by a rubber stamp.
    assert "echoes the identifiers its skill requires" in agent_use
    # Host-wide unavailability must keep its own, broader rule.
    assert "unavailable in the host at all" in agent_use

    # Each dispatching pass names the artifact whose receipt completes it.
    for skill_id, heading in DISPATCH_SECTION_BY_SKILL.items():
        section = _section(raw, heading)
        assert section, heading
        assert SKILL_BY_ID[skill_id].output in section, (heading, skill_id)

    # Detecting a lost dispatch is worthless if the user is never told.
    for document in (implementation, report):
        assert "every role dispatch that delivered no artifact" in document
        assert "which roles ran degraded as a result" in document

    # Portability: the mechanism is one host's, the contract is four hosts'.
    shipped = list((ROOT / "plugins").rglob("SKILL.md"))
    shipped += list((ROOT / "plugins").rglob("agents/*.yaml"))
    assert len(shipped) > len(DISPATCHED_ROLE_SKILLS), "no shipped contracts found"
    for path in shipped:
        text = path.read_text(encoding="utf-8")
        for token in HOST_MECHANISM_TOKENS:
            assert token not in text, f"{path.name} names a host mechanism: {token}"


def test_every_dispatched_role_skill_states_that_producing_is_not_delivering():
    # Agent Use binds the coordinator, which is the side that did not fail. A
    # dispatched role reads only its own atomic skill, and these skills are also
    # invocable directly, so the clause is conditioned on being dispatched
    # rather than asserting a coordinator always exists. Derived from the
    # registry so adding a dispatched role without the clause fails here.
    skill_root = ROOT / "plugins" / "dev-workflows" / "skills"

    for skill_id in DISPATCHED_ROLE_SKILLS:
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
    assert expected_version == "2.0.0"

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

    implementation = implementation_path.read_text(encoding="utf-8")
    commit = commit_path.read_text(encoding="utf-8")
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
    implementation = (skill_root / "implementation-skill" / "SKILL.md").read_text(
        encoding="utf-8"
    )
    commit = (skill_root / "commit-atomic-change" / "SKILL.md").read_text(
        encoding="utf-8"
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
