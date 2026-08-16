from __future__ import annotations

import json
import os
import re
import shlex
import subprocess
import sys
from pathlib import Path

import pytest

from agent_workflows_harness import cli
from agent_workflows_harness.models import RequestFacts
from agent_workflows_harness.ontology import (
    DEFAULT_ONTOLOGY,
    Ontology,
    derive,
    derived_properties,
    load_ontology,
    subsumption_path,
)
from agent_workflows_harness.registry import SKILLS
from agent_workflows_harness.selector import select_skills
from agent_workflows_harness.serialization import plan_to_dict


ROOT = Path(__file__).resolve().parents[1]


def _subprocess_env() -> dict[str, str]:
    env = os.environ.copy()
    current = env.get("PYTHONPATH")
    src_path = str(ROOT / "src")
    env["PYTHONPATH"] = src_path if not current else f"{src_path}{os.pathsep}{current}"
    return env


def _run_cli(*argv: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-m", "agent_workflows_harness.cli", *argv],
        capture_output=True,
        text=True,
        env=_subprocess_env(),
        cwd=ROOT,
    )


def test_subclass_closure_derives_shared_behavior_without_the_keyword():
    # "session_module" contains no keyword the regex classifier knows; the
    # property comes from AuthSurface being subsumed by SharedBehavior.
    assert derived_properties(["session_module"]) == frozenset({"touches_shared_behavior"})


def test_derivation_reports_the_subsumption_path():
    (derivation,) = derive(["session_module"])

    assert derivation.request_property == "touches_shared_behavior"
    assert derivation.source == "touches(req, session_module)"
    assert derivation.path == ("session_module", "AuthSurface", "SharedBehavior")


def test_subsumption_path_is_the_shortest_chain():
    assert subsumption_path(DEFAULT_ONTOLOGY, "migration", "Surface") == (
        "migration",
        "PersistenceSurface",
        "SharedBehavior",
        "Surface",
    )


def test_scope_triples_derive_scope_properties():
    assert derived_properties([], ["one_line"]) == frozenset({"trivial"})
    assert derived_properties([], ["cross_module"]) == frozenset({"multi_file"})


def test_docs_only_requires_every_surface_to_be_documentation():
    assert "docs_only" in derived_properties(["readme", "changelog"])
    assert "docs_only" not in derived_properties(["readme", "auth_module"])


def test_external_service_surface_is_not_shared_behavior():
    properties = derived_properties(["github_api"])

    assert properties == frozenset({"external_service"})


def test_no_triples_derive_nothing():
    assert derive([], []) == ()


def test_unknown_surface_is_rejected():
    with pytest.raises(ValueError, match="unknown surface"):
        derive(["nonexistent_module"])


def test_unknown_scope_is_rejected():
    with pytest.raises(ValueError, match="unknown scope"):
        derive([], ["gigantic"])


def test_ontology_rejects_subclass_cycles():
    with pytest.raises(ValueError, match="cycle"):
        Ontology(
            sub_class_of=(("A", "B"), ("B", "A")),
            surface_class=(),
            skill_class=(),
            property_of_class=(),
            scope_property=(),
        )


def test_ontology_rejects_undeclared_classes():
    with pytest.raises(ValueError, match="undeclared classes"):
        Ontology(
            sub_class_of=(("A", "B"),),
            surface_class=(("thing", "C"),),
            skill_class=(),
            property_of_class=(),
            scope_property=(),
        )


def test_ontology_rejects_unsupported_request_properties():
    with pytest.raises(ValueError, match="unsupported request properties"):
        Ontology(
            sub_class_of=(("A", "B"),),
            surface_class=(),
            skill_class=(),
            property_of_class=(("A", "not_a_property"),),
            scope_property=(),
        )


def test_ontology_rejects_malformed_terms():
    with pytest.raises(ValueError, match="must start with a letter"):
        Ontology(
            sub_class_of=(("1bad", "B"),),
            surface_class=(),
            skill_class=(),
            property_of_class=(),
            scope_property=(),
        )


def test_default_ontology_classifies_every_registry_skill():
    classified = {skill_id for skill_id, _ in DEFAULT_ONTOLOGY.skill_class}

    assert classified == {skill.skill_id for skill in SKILLS}


def test_ontology_document_roundtrip(tmp_path: Path):
    path = tmp_path / "tbox.json"
    path.write_text(json.dumps(DEFAULT_ONTOLOGY.to_dict()), encoding="utf-8")

    assert load_ontology(path) == DEFAULT_ONTOLOGY


def test_load_ontology_rejects_invalid_json(tmp_path: Path):
    path = tmp_path / "tbox.json"
    path.write_text("{not json", encoding="utf-8")

    with pytest.raises(ValueError, match="not valid JSON"):
        load_ontology(path)


def test_load_ontology_rejects_unsupported_keys(tmp_path: Path):
    path = tmp_path / "tbox.json"
    path.write_text(json.dumps({"surprise": []}), encoding="utf-8")

    with pytest.raises(ValueError, match="unsupported keys"):
        load_ontology(path)


def test_custom_ontology_extends_the_vocabulary_without_code_changes():
    extended = Ontology(
        sub_class_of=DEFAULT_ONTOLOGY.sub_class_of,
        surface_class=DEFAULT_ONTOLOGY.surface_class + (("billing_ledger", "PersistenceSurface"),),
        skill_class=DEFAULT_ONTOLOGY.skill_class,
        property_of_class=DEFAULT_ONTOLOGY.property_of_class,
        scope_property=DEFAULT_ONTOLOGY.scope_property,
    )

    assert derived_properties(["billing_ledger"], [], extended) == frozenset(
        {"touches_shared_behavior"}
    )


def test_ontology_facts_select_the_gates_the_keyword_classifier_drops():
    inferred = derived_properties(["session_module"], ["one_line"])
    facts = RequestFacts.from_properties(inferred)

    selected = {skill.skill_id for skill in select_skills(facts)}

    # Concrete risk evidence still wins over the caller's "one line" hint.
    assert "trivial" not in facts.properties
    assert {"create-implementation-plan", "critique-plan", "run-broad-tests"} <= selected


def test_plan_to_dict_omits_derived_key_without_ontology_facts():
    from agent_workflows_harness.selector import select_plan

    payload = plan_to_dict(select_plan(RequestFacts.from_properties({"trivial"})))

    assert "derived" not in payload


def test_cli_reports_derived_facts_as_json():
    result = _run_cli("--touches", "session_module", "--scope", "one_line")

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    derived = {entry["property"]: entry for entry in payload["derived"]}

    assert derived["touches_shared_behavior"]["path"] == (
        "session_module -> AuthSurface -> SharedBehavior"
    )
    assert payload["blocked"] == []


def test_cli_rejects_unknown_surface():
    result = _run_cli("--touches", "nonexistent_module")

    assert result.returncode != 0
    assert "unknown surface" in result.stderr


def test_cli_combines_text_and_ontology_facts():
    result = _run_cli("add docs only", "--touches", "github_api")

    assert result.returncode != 0
    assert "docs_only conflicts" in result.stderr


def test_cli_prints_the_active_ontology_as_a_loadable_document():
    # Round-trip against DEFAULT_ONTOLOGY, not against a re-serialization of the
    # output: that would be self-consistent and anchored to nothing. Ontology is
    # a frozen dataclass over tuples, so equality fails on a dropped, added, or
    # reordered row -- a caller reading a truncated vocabulary concludes exactly
    # the wrong thing about what it may declare.
    result = _run_cli("--print-ontology")

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert Ontology.from_dict(payload) == DEFAULT_ONTOLOGY
    assert set(payload) == set(DEFAULT_ONTOLOGY.to_dict())
    # Round-trip equality is whitespace- and order-blind, so the shape the docs
    # show is pinned separately: dropping indent or sort_keys would leave the
    # example diverged from the real output with every assertion still green.
    assert result.stdout == json.dumps(payload, indent=2, sort_keys=True) + "\n", (
        "the docs show a pretty-printed, key-sorted document; sort_keys also "
        "carries the documented relation order on the JSON side"
    )
    # A successful run that selects nothing, so a caller reading `selected`
    # fails loudly instead of reading a TBox as an empty plan.
    assert "selected" not in payload and "blocked" not in payload


def test_printed_ontology_reflects_the_supplied_tbox_not_the_default(tmp_path: Path):
    custom = Ontology(
        sub_class_of=(("BillingSurface", "Surface"),),
        surface_class=(("billing_ledger", "BillingSurface"),),
        skill_class=(),
        property_of_class=(("BillingSurface", "touches_shared_behavior"),),
        scope_property=(),
    )
    # Without this the fixture could drift into equality with the default and
    # make the assertion below vacuous.
    assert custom != DEFAULT_ONTOLOGY
    path = tmp_path / "tbox.json"
    path.write_text(json.dumps(custom.to_dict()), encoding="utf-8")

    result = _run_cli("--ontology", str(path), "--print-ontology")

    assert result.returncode == 0, result.stderr
    assert Ontology.from_dict(json.loads(result.stdout)) == custom


def test_an_unloadable_ontology_is_rejected_before_anything_is_printed(tmp_path: Path):
    # Pins the branch placement after the load: a document that did not load
    # cannot be printed. Hoisting the branch to the top of main() breaks this.
    path = tmp_path / "broken.json"
    path.write_text("{not json", encoding="utf-8")

    result = _run_cli("--ontology", str(path), "--print-ontology")

    assert result.returncode == 2
    assert result.stdout == ""
    assert "not valid JSON" in result.stderr


def test_printing_the_ontology_ignores_the_rest_of_the_request(tmp_path: Path):
    log = tmp_path / "decisions.jsonl"
    baseline = _run_cli("--print-ontology")

    result = _run_cli(
        "refactor auth workflow",
        "--property", "trivial",
        "--touches", "nonexistent_module",
        # --scope too: it is named as ignored in the help entry, and without it
        # in this argv that category claim is the one nothing executes.
        "--scope", "nonexistent_scope",
        "--decision-log", str(log),
        "--print-ontology",
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout == baseline.stdout
    # The undeclared surface is deliberately not validated: the caller reaching
    # for this flag is usually the one whose name was just rejected.
    assert "nonexistent_module" not in result.stderr
    # No selection happened, so there is no record -- but a supplied flag is
    # never dropped in silence.
    assert not log.exists()
    assert "decision log not written" in result.stderr


def test_docs_show_a_printable_ontology_document_that_is_not_stale():
    # "It loads" is not a test: Ontology.from_dict({}) succeeds, so an example
    # truncated to nothing would pass. Assert the relation names are complete
    # and every row shown is a real row, which permits an abridged example
    # while failing one that names a surface that was renamed or removed.
    doc = (ROOT / "docs" / "how-it-works.md").read_text(encoding="utf-8")
    expected = DEFAULT_ONTOLOGY.to_dict()

    documented = []
    for block in re.findall(r"```json\n(.*?)\n```", doc, re.DOTALL):
        try:
            parsed = json.loads(block)
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict) and set(parsed) == set(expected):
            documented.append(parsed)

    # The text example is exactly as staleable as the JSON one: rename a
    # surface and it silently lies. Same subset check, parsed the way the
    # renderer writes it.
    shown_rows = 0
    # Anchor on line starts: an unanchored fence pattern begins matching at a
    # *closing* fence and yields empty blocks.
    # `[^\n]*`, not `[a-z]*`: a tag the class cannot match makes the engine skip
    # that opener and start at the fence's *closing* delimiter, which is the
    # pairing break this scan already had twice, relocated into the tag class.
    fence = r"^[ \t]*```([^\n]*)\n(.*?)^[ \t]*```"
    for tag, block in re.findall(fence, doc, re.DOTALL | re.MULTILINE):
        # Only untagged fences: the renderer's output is untagged, and a JSON
        # fence contains `"path": "a -> b"` lines that would otherwise be read
        # as rows. Untagged fences that are not rows (the text-mode error
        # example) carry no ` -> ` and drop out below.
        if tag:
            continue
        for line in block.splitlines():
            relation, sep, rest = line.partition(": ")
            left, arrow, right = rest.partition(" -> ")
            if not sep or not arrow:
                continue
            # Resolve every `x: y -> z` line rather than skipping unknown
            # relations: skipping would let a mistyped relation name drop out
            # of the count in silence.
            assert relation in expected, (
                f"{line!r} parses as a TBox row but names no relation; "
                "tag the fence if it is not one"
            )
            assert (left, right) in {tuple(row) for row in expected[relation]}, line
            shown_rows += 1
    assert shown_rows, "the docs no longer show a text-rendered ontology example"

    assert documented, "the docs no longer show a printable ontology document"
    for parsed in documented:
        for relation, rows in parsed.items():
            # Abridging is fine -- the real document is 51 rows -- but an
            # example truncated to nothing would still satisfy a subset check
            # while teaching a reader nothing about the vocabulary.
            assert rows, f"the documented {relation} example is empty"
            shown = {tuple(row) for row in rows}
            assert shown <= {tuple(row) for row in expected[relation]}, relation


def test_printed_ontology_text_mode_carries_the_whole_tbox():
    # Set equality per relation, not tuple equality: pinning row order would
    # fail a harmless later sort though no information changed. The line count
    # is derived, never hardcoded -- a literal goes stale in silence and pins
    # nothing about correctness. Completeness is the property that matters,
    # because a caller reading a truncated vocabulary concludes exactly the
    # wrong thing about what it may declare.
    result = _run_cli("--print-ontology", "--text")

    assert result.returncode == 0, result.stderr
    expected = DEFAULT_ONTOLOGY.to_dict()
    lines = result.stdout.splitlines()
    assert len(lines) == sum(len(rows) for rows in expected.values())

    # The docs promise text and JSON agree on relation order. Nothing else
    # pinned it, so switching to declaration order would keep the set
    # comparison below green while breaking a documented claim.
    order = [line.partition(": ")[0] for line in lines]
    assert order == sorted(order)

    # The format's unambiguity rests on terms never containing a space, a
    # colon, or '>'. That coupling lives in a comment and in the docs; widening
    # _TERM_PATTERN would make the shipped output unparseable and the claim
    # false while every assertion above still passed.
    # Through the public constructor rather than the module-private pattern:
    # this pins the behaviour end to end, and a renamed regex fails as an
    # assertion here instead of as an import error.
    for hostile in ("a b", "a:b", "a->b", "a>b"):
        with pytest.raises(ValueError, match="must start with a letter"):
            Ontology(
                sub_class_of=((hostile, "Surface"),),
                surface_class=(),
                skill_class=(),
                property_of_class=(),
                scope_property=(),
            )

    rebuilt: dict[str, set[tuple[str, str]]] = {}
    for line in lines:
        relation, sep, rest = line.partition(": ")
        assert sep, line
        left, arrow, right = rest.partition(" -> ")
        assert arrow, line
        rebuilt.setdefault(relation, set()).add((left, right))

    assert rebuilt == {
        relation: {tuple(row) for row in rows}
        for relation, rows in expected.items()
        if rows
    }


def test_a_rejected_fact_points_at_the_flag_that_lists_the_vocabulary():
    # The caller is reading stderr at this moment, not --help, and the message
    # named the relation to declare in but never the values it accepts. Both
    # vocabulary errors are covered, which is what keeps visible the fact that
    # the hint decorates every ValueError derive() raises.
    for flag, bad in (("--touches", "nonexistent_module"), ("--scope", "nonexistent_scope")):
        result = _run_cli(flag, bad)

        assert result.returncode == 2, (flag, result.stdout)
        assert result.stdout == ""
        assert bad in result.stderr, flag
        # The whole hint, not the flag name: argparse prints a usage line that
        # already contains `[--print-ontology]` because the flag exists, so
        # asserting the name alone stays green with the hint deleted entirely.
        assert "run --print-ontology to list the declared vocabulary" in result.stderr, flag


def test_the_rejection_hint_names_the_tbox_that_did_the_rejecting(tmp_path: Path):
    # Without the path, a caller whose custom TBox rejected them follows the
    # hint and reads the bundled default -- a vocabulary with nothing to do
    # with the one that refused them, and authoritative-looking.
    custom = Ontology(
        sub_class_of=(("BillingSurface", "Surface"),),
        surface_class=(("billing_ledger", "BillingSurface"),),
        skill_class=(),
        property_of_class=(("BillingSurface", "touches_shared_behavior"),),
        scope_property=(),
    )
    assert custom != DEFAULT_ONTOLOGY
    # A space and an apostrophe: the hint is a command a caller pastes back, and
    # tmp_path alone carries neither, so quoting and escaping would both go
    # unpinned. An apostrophe is what separates correct quoting from quoting
    # that merely happens to be invertible.
    directory = tmp_path / "o'brien tbox"
    directory.mkdir()
    path = directory / "tbox.json"
    path.write_text(json.dumps(custom.to_dict()), encoding="utf-8")

    # Both vocabulary errors, as the sibling test loops them: the carry-through
    # rides on one `parser.error` call, and covering only one hides that.
    for flag, bad in (("--touches", "session_module"), ("--scope", "one_line")):
        rejected = _run_cli("--ontology", str(path), flag, bad)
        assert rejected.returncode == 2, flag
        # Against the hint, for the same reason as below: a TBox that failed to
        # load also exits 2 and names the path, so asserting on the whole
        # stream would hold with no hint involved at all -- the fixture
        # loading, rather than the assertion, would be doing the work.
        rejected_hint = rejected.stderr.strip().splitlines()[-1].split("; ")[-1]
        assert str(path) in rejected_hint, flag
        # Not redundant with the identical assertion further down, and not
        # duplication to remove: a load failure carries no "; ", so the split
        # above returns the whole line and the path assertion still holds. This
        # is the line that separates "the carry-through works for both error
        # kinds" from "the ontology never loaded".
        assert "--print-ontology" in rejected_hint, flag

    result = _run_cli("--ontology", str(path), "--touches", "session_module")

    assert result.returncode == 2
    # Against the hint, never against the whole stream: argparse prints a usage
    # block listing every registered flag, so `"--print-ontology" in stderr`
    # holds even when the hint never mentions it. That exact line shipped here
    # and is what the house rule at the top of test_plugin_package.py is about.
    hint = result.stderr.strip().splitlines()[-1].split("; ")[-1]
    # The path, not a particular quoting style: asserting the exact output of
    # the quoting function would make the expected value the implementation.
    assert str(path) in hint
    assert "--print-ontology" in hint
    # `--ontology=<path>`, never a separate argument: a relative path beginning
    # with `-` is a legal filename that argparse would read as another option,
    # and quoting cannot fix it because the shell is not what breaks. Asserted
    # as the separator alone, so the quoting style stays unpinned here.
    assert "--ontology=" in hint

    # Parsing the hint back must reach the same TBox that did the rejecting.
    # This reads it the way a POSIX shell would; it is evidence about that
    # reading, not about every shell the hint might be pasted into.
    # removeprefix/removesuffix are no-ops on a mismatch, so a reworded hint
    # would leave the trailing words on the argv, where the positional request
    # swallows them -- and this would quietly stop being a paste-back check.
    assert hint.startswith("run ") and hint.endswith(" to list the declared vocabulary")
    argv = shlex.split(hint.removeprefix("run ").removesuffix(" to list the declared vocabulary"))
    echoed = _run_cli(*argv)
    assert echoed.returncode == 0, echoed.stderr
    assert Ontology.from_dict(json.loads(echoed.stdout)) == custom


def test_the_documented_composition_rule_matches_what_the_flag_actually_does(tmp_path: Path):
    # The help string and the docs are the one place a caller learns the
    # composition semantics, and the first version of both said "every other
    # argument is ignored" while --text changed the output and --decision-log
    # warned. A contract that contradicts itself is worse than none, and this
    # change exists to make the contract readable.
    honoured = _run_cli("--print-ontology", "--text")
    assert honoured.returncode == 0, honoured.stderr
    assert honoured.stdout != _run_cli("--print-ontology").stdout, "--text is honoured"

    # tmp_path, not a relative name: _run_cli runs with cwd=ROOT, so a
    # regression that wrote the log would drop a stray file in the repo root
    # while this test still passed on stderr alone.
    log = tmp_path / "unused.jsonl"
    warned = _run_cli("--print-ontology", "--decision-log", str(log))
    assert "decision log not written" in warned.stderr, "--decision-log is not ignored"
    assert not log.exists()

    # Read the flag's own help entry, not the whole --help dump: argparse lists
    # --ontology and --text as their own entries regardless, so asserting they
    # appear anywhere would hold no matter what this flag claims.
    (action,) = [a for a in cli._parser()._actions if a.dest == "print_ontology"]
    own_help = " ".join(action.help.split())
    assert "Honours --ontology and --text" in own_help
    assert "a supplied --decision-log warns and writes nothing" in own_help
    assert "every other argument is ignored" not in own_help

    # Every argument the parser accepts must be classified by that entry, so a
    # flag added later cannot land in neither category unnoticed.
    for other in cli._parser()._actions:
        if other.dest in {"help", "print_ontology"}:
            continue
        # Every alias, not just the first: adding `-o` to --ontology would
        # otherwise leave `-o` accepted by the parser and classified nowhere,
        # which is broader than what checking option_strings[0] proves.
        for name in other.option_strings or ["request text"]:
            # Boundary-aware: a plain substring test passes vacuously for any
            # name contained in a longer one, so `-o` would be "found" inside
            # `--ontology`. \b is not enough -- a trailing hyphen is itself a
            # word boundary, so `--decision` would match `--decision-log`.
            assert re.search(re.escape(name) + r"(?![\w-])", own_help), (
                f"{name} is neither honoured nor ignored"
            )

    doc = " ".join((ROOT / "docs" / "how-it-works.md").read_text(encoding="utf-8").split())
    assert "`--ontology` and `--text` still apply" in doc
    assert "a supplied `--decision-log` warns on stderr" in doc
    assert "Every argument other than `--ontology` is ignored" not in doc


def test_a_quoted_path_survives_every_shell_the_hint_may_be_pasted_into():
    # The paste-back test reads the hint the way a POSIX shell would, so it is
    # structurally blind to cmd and PowerShell. This runs no shell either: it
    # pins shape proxies that stand in for a measurement recorded in the commit
    # that introduced the quoting, where the emitted string was pasted into all
    # three. The last assertion below is shlex reading its own output, so treat
    # this as a regression guard on the shape, not as evidence about a shell.
    plain = "/home/me/tbox.json"
    assert cli._quote_path(plain) == plain, "a bare-safe path should not be quoted"

    for hostile in (
        "C:" + chr(92) + "git" + chr(92) + "tbox.json",       # backslashes alone
        "C:" + chr(92) + "my tbox" + chr(92) + "t.json",      # a space
        "C:" + chr(92) + "o'brien" + chr(92) + "t.json",      # an apostrophe
        "C:" + chr(92) + "o'brien tbox" + chr(92) + "t.json",
        # A POSIX spaced path: every case above also carries a backslash, so
        # the space rule was forced by the backslash and would have gone
        # unpinned on a platform without one.
        "/home/me/my tbox/t.json",
        # The only case that exercises the escaping branch. Illegal in a
        # Windows filename, legal on POSIX, where this CLI also runs.
        '/home/me/od"d/t.json',
    ):
        quoted = cli._quote_path(hostile)
        assert quoted.startswith('"') and quoted.endswith('"'), hostile
        # Double quotes, because cmd treats the POSIX single-quote form as
        # literal text and PowerShell mis-reads its apostrophe escaping.
        assert "'\"'\"'" not in quoted, hostile
        # Backslashes stay literal inside double quotes in all three shells,
        # so the path survives verbatim unless it carries a quote of its own.
        if '"' not in hostile:
            assert hostile in quoted, hostile
        else:
            assert '\\"' in quoted, hostile
        assert shlex.split(quoted) == [hostile], hostile
