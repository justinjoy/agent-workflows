"""The mutation runner's own oracle, validated rather than asserted.

`tests/mutations.py` is a harness that reports whether a tripwire fired. Its
green line is a claim, and the issue that motivated it records three separate
people shipping a *broken* mutation runner while hunting this exact defect
class -- each one reading as "all caught". A green line produced by a broken
mutation is indistinguishable from one produced by a vacuous assertion, so the
runner is not trusted on its own word here.

Every canary below drives `probe()` -- the runner's only verdict path, and the
table's only caller -- against a generated fixture whose correct verdict is
known, and asserts the **exact** verdict. The fixtures live in a temporary
directory, and two different things keep them there: `run_table` and
`emit_expect` each take a single `root`, so pointing at one tree while grading
another is unrepresentable rather than merely unused; and
`the_working_tree_is_untouched` below catches a mutation that survives the
session. The first is what protects the working tree. The second is narrower
than it first looks and its docstring says so -- crediting it with the first's
job would point the next reader at the weaker of the two.

The two that carry the weight:

- `test_a_vacuous_test_comes_back_survived`. A runner that reports everything
  as caught reports this as CAUGHT and this file goes red. That is the property
  every ad-hoc attempt lost.
- `test_a_failure_for_the_wrong_reason_is_not_caught`. The `expect` comparison
  is the runner's third defence, and it is the one no other canary exercises:
  CAUGHT, SURVIVED, BROKEN, STALE and NO_SUCH_TEST are all reached without
  `expect` ever needing to discriminate, so a degraded comparison -- inverted,
  matched against the wrong element, or short-circuited -- would pass all five
  and leave every table entry reading CAUGHT. Without this canary, that whole
  layer is unvalidated.
"""

from __future__ import annotations

import ast
import importlib.util
import os
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def _load_runner():
    """Import `tests/mutations.py` by path.

    Not `import mutations`. That works only because `tests/` has no
    `__init__.py` and pytest therefore puts this directory on `sys.path` -- a
    mechanism that depends on the *absence* of a file, so adding one would
    break this gate for a reason no message would explain.
    """

    spec = importlib.util.spec_from_file_location("_mutations", ROOT / "tests" / "mutations.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["_mutations"] = module
    spec.loader.exec_module(module)
    return module


mutations = _load_runner()


@pytest.fixture(scope="module", autouse=True)
def the_working_tree_is_untouched():
    """Fail the session if any file the table can mutate is left changed.

    Be precise about what this does and does not catch, because the first
    version of this docstring was not. It compares bytes before and after the
    session, so it catches a mutation that **survives**. It cannot catch one
    that is applied and restored mid-session -- `probe` restores what it
    mutates, so a canary that graded the real repository by mistake would come
    and go between these two reads and this fixture would say nothing.
    Measured: exactly that canary, injected, left the session green.

    What protects against grading the wrong tree is `run_table` taking a single
    `root`, which makes the divergence unrepresentable rather than merely
    unused. Crediting this fixture for that would point the next reader at the
    weaker of the two, which is how the one that matters gets deleted.

    What this adds is the narrow case the collapse cannot reach: a restore that
    silently did not happen. `_restore` already raises on a verified-bad
    restore, so the window is small -- and small is not nothing, since it is
    the difference between a developer's tree being wrong and being told so.

    Derived from the table rather than hardcoded, so a new entry is covered the
    day it lands. See `watched_targets` for why the derivation is guarded
    before the constant joins it.
    """

    before = {path: path.read_bytes() for path in watched_targets()}
    yield
    changed = [str(path) for path, payload in before.items() if path.read_bytes() != payload]
    assert not changed, f"the self-check modified the working tree: {changed}"


def watched_targets() -> list[Path]:
    """Every file the table can mutate, plus the one it always could.

    The derived set is guarded **before** the constant joins it. A first
    version appended `cli.py` and then asserted the list was non-empty, which
    is true by construction -- so a derivation returning nothing passed, with
    a message that said "no targets derived" while testing a list that had a
    constant added to it. That is the same group-A shape this guard exists to
    prevent, inside the guard, in the commit that closed the previous
    instance. `test_the_watched_set_is_empty_without_a_table` is its falsifier.
    """

    derived = sorted({ROOT / item.target for item in mutations.load_table()})
    assert derived, "no targets derived from the table; this fixture would watch only cli.py"
    always = ROOT / "src" / "agent_workflows_harness" / "cli.py"
    assert always.exists(), "the constant target is gone; this fixture watches less than it says"
    return sorted(set(derived) | {always})


SUBJECT = '''
def quote(value):
    """Quote a value that needs it. The behaviour every canary mutates."""

    if " " in value:
        return '"' + value + '"'
    return value
'''

TEST_SUBJECT = '''
import pytest

from subject import quote


def test_a_spaced_value_is_quoted():
    assert quote("a b") == '"a b"', "spaced value must be quoted"


def test_that_asserts_nothing_about_quoting():
    # Deliberately vacuous: true whether or not quoting works. This is the
    # shape the whole mechanism exists to detect.
    assert quote("a b") is not None


def test_that_goes_red_without_naming_the_reason():
    # Passes on the clean tree, and the mutation does break it -- but its
    # failure message says nothing about quoting, so an entry claiming the
    # quoting message must not be credited with catching it.
    assert len(quote("a b")) == 5, "length changed"


def test_that_is_already_red_before_any_mutation():
    assert 1 == 2, "unrelated arithmetic"


def test_whose_source_echoes_another_tests_message():
    # The literal below is another test's `expect`, and it sits above the
    # failing assertion, so pytest's longrepr echoes it while this test's own
    # failure message says something else entirely. This is the fixture that
    # makes the message/longrepr choice observable: matched against the
    # longrepr this reads as CAUGHT, matched against the message attribute it
    # reads as WRONG_REASON. Modelled on the real shape in
    # tests/test_ontology.py, where two fixture literals share one tuple above
    # every assertion in the function.
    borrowed = "spaced value must be quoted"
    assert borrowed
    assert len(quote("a b")) == 5, "length is not the quoting message"


@pytest.fixture
def quoted():
    # Raises during setup when quoting is deleted, so the test below never
    # runs its own assertion. JUnit records that as <error>, not <failure>.
    value = quote("a b")
    assert value == '"a b"', "fixture could not build its value"
    return value


def test_that_depends_on_a_fixture(quoted):
    assert quoted.endswith('"')
'''

# The mutation every canary applies: quoting stops happening.
DELETE_QUOTING = ('if " " in value:', "if False:")
SPACED = "test_subject.py::test_a_spaced_value_is_quoted"


@pytest.fixture
def workspace(tmp_path: Path) -> Path:
    # `subject.py` goes in a subdirectory, not beside the test. `python -c`
    # puts the working directory on sys.path, so with the module in `cwd` the
    # import oracle would succeed whether or not `_import_check` sets
    # PYTHONPATH -- the guard would be correct and unfalsifiable from every
    # direction, which is the standard this file holds everything else to.
    # From `lib/`, deleting that line makes the import fail and every probe
    # here returns BROKEN instead of its expected verdict.
    (tmp_path / "lib").mkdir()
    (tmp_path / "lib" / "subject.py").write_text(SUBJECT, encoding="utf-8")
    (tmp_path / "test_subject.py").write_text(TEST_SUBJECT, encoding="utf-8")
    # pytest itself needs to resolve `from subject import quote`, and it uses
    # its own rule rather than the runner's.
    (tmp_path / "pytest.ini").write_text("[pytest]\npythonpath = lib\n", encoding="utf-8")
    return tmp_path


def _probe(workspace: Path, *, old: str, new: str, nodeid: str, expect: str):
    return mutations.probe(
        workspace / "lib" / "subject.py",
        old,
        new,
        nodeid,
        expect,
        importable=("subject", workspace / "lib"),
        cwd=workspace,
    )


def test_a_real_tripwire_comes_back_caught(workspace: Path):
    verdict = _probe(
        workspace,
        old=DELETE_QUOTING[0],
        new=DELETE_QUOTING[1],
        nodeid=SPACED,
        expect="spaced value must be quoted",
    )
    assert verdict.name == mutations.CAUGHT, verdict.detail


def test_a_vacuous_test_comes_back_survived(workspace: Path):
    # The crux. A runner that mis-invokes pytest, reads an exit code, or
    # otherwise grades something that is not the named test's record reports
    # this as CAUGHT. It must report SURVIVED: the behaviour was deleted and
    # this test did not notice.
    verdict = _probe(
        workspace,
        old=DELETE_QUOTING[0],
        new=DELETE_QUOTING[1],
        nodeid="test_subject.py::test_that_asserts_nothing_about_quoting",
        expect="spaced value must be quoted",
    )
    assert verdict.name == mutations.SURVIVED, verdict.detail


def test_a_failure_for_the_wrong_reason_is_not_caught(workspace: Path):
    # The only canary that makes the `expect` comparison do work. The named
    # test does go red, but for a reason this entry does not claim, so
    # crediting the entry with catching the mutation would be the table-level
    # form of "some test failed" standing in for "this assertion caught it".
    verdict = _probe(
        workspace,
        old=DELETE_QUOTING[0],
        new=DELETE_QUOTING[1],
        nodeid="test_subject.py::test_that_goes_red_without_naming_the_reason",
        expect="spaced value must be quoted",
    )
    assert verdict.name == mutations.WRONG_REASON, verdict.detail


def test_a_failure_whose_source_echoes_another_expect_is_not_caught(workspace: Path):
    # Oracle 4, and the only canary that can see which element `expect` is
    # matched against. The named test's longrepr contains the expect string as
    # a source literal; its failure message does not. Matching the longrepr --
    # the exact degradation the module docstring says it defends against --
    # turns this CAUGHT, and every other canary stays green through it.
    verdict = _probe(
        workspace,
        old=DELETE_QUOTING[0],
        new=DELETE_QUOTING[1],
        nodeid="test_subject.py::test_whose_source_echoes_another_tests_message",
        expect="spaced value must be quoted",
    )
    assert verdict.name == mutations.WRONG_REASON, verdict.detail


def test_a_target_that_is_not_python_skips_only_the_import_oracle(workspace: Path):
    # `module=None` is how a document or a manifest is mutated: "it still
    # imports" means nothing about Markdown. No table entry uses it yet, so
    # without this canary the branch is dead code justified by prose.
    document = workspace / "notes.md"
    document.write_text("the flag is --alpha\n", encoding="utf-8")
    (workspace / "test_doc.py").write_text(
        "from pathlib import Path\n\n\n"
        "def test_the_document_names_the_flag():\n"
        "    text = Path(__file__).parent.joinpath('notes.md').read_text(encoding='utf-8')\n"
        "    assert '--alpha' in text, 'the document stopped naming the flag'\n",
        encoding="utf-8",
    )
    verdict = mutations.probe(
        document,
        "--alpha",
        "--beta",
        "test_doc.py::test_the_document_names_the_flag",
        "the document stopped naming the flag",
        importable=None,
        cwd=workspace,
    )
    assert verdict.name == mutations.CAUGHT, verdict.detail


def test_a_test_that_is_already_red_grades_nothing(workspace: Path):
    # Oracle 5, the inner half. A mutation measured against an already-failing
    # test says nothing about the mutation, so the runner must refuse to grade
    # it rather than record a red as a catch.
    verdict = _probe(
        workspace,
        old=DELETE_QUOTING[0],
        new=DELETE_QUOTING[1],
        nodeid="test_subject.py::test_that_is_already_red_before_any_mutation",
        expect="spaced value must be quoted",
    )
    assert verdict.name == mutations.BASELINE_RED, verdict.detail


def test_a_setup_failure_is_not_a_tripwire_firing(workspace: Path):
    # JUnit distinguishes <error> from <failure>, and the difference matters:
    # the test's own assertion never ran, so it proved nothing about the
    # mutation. Pinned because rejecting <error> is load-bearing in the
    # runner and would otherwise be unexercised.
    verdict = _probe(
        workspace,
        old=DELETE_QUOTING[0],
        new=DELETE_QUOTING[1],
        nodeid="test_subject.py::test_that_depends_on_a_fixture",
        expect="spaced value must be quoted",
    )
    assert verdict.name == mutations.ERRORED, verdict.detail


def test_a_mutation_that_does_not_parse_is_not_caught(workspace: Path):
    # A syntax error is a mutation that did not happen. Reading the resulting
    # red as "the tripwire fired" is one of the three real broken runners the
    # issue records.
    verdict = _probe(
        workspace,
        old="return value",
        new="return value +",
        nodeid=SPACED,
        expect="spaced value must be quoted",
    )
    assert verdict.name == mutations.BROKEN, verdict.detail


def test_an_anchor_that_no_longer_exists_is_stale_not_green(workspace: Path):
    verdict = _probe(
        workspace,
        old="this text is not in the subject",
        new="nor is this",
        nodeid=SPACED,
        expect="spaced value must be quoted",
    )
    assert verdict.name == mutations.STALE, verdict.detail


def test_an_anchor_matching_twice_is_ambiguous_not_green(workspace: Path):
    # Which site was mutated decides which behaviour was deleted, so a verdict
    # about "the mutation" is meaningless when two sites matched.
    #
    # `new` must differ from `old`: an earlier version of this canary passed
    # old="value", new="value", which tripped the old-equals-new guard and
    # returned STALE without ever counting occurrences. It accepted either
    # verdict, so it was green on the wrong branch, and the AMBIGUOUS branch
    # could be deleted outright with the whole self-check still passing. That
    # is issue #12's group B -- a fixture that names its case and never runs it
    # -- inside the file built to catch it. Assert the one verdict, not a set.
    verdict = _probe(
        workspace,
        old="value",
        new="valu3",
        nodeid=SPACED,
        expect="spaced value must be quoted",
    )
    assert verdict.name == mutations.AMBIGUOUS, verdict.detail


def test_an_entry_that_mutates_nothing_is_stale(workspace: Path):
    verdict = _probe(
        workspace,
        old="value",
        new="value",
        nodeid=SPACED,
        expect="spaced value must be quoted",
    )
    assert verdict.name == mutations.STALE, verdict.detail


def test_an_empty_expect_cannot_make_a_failure_caught(workspace: Path):
    # `"" in message` is always true, so an empty expect would turn every red
    # into a catch. Refused in `probe` rather than only in the table lint,
    # because `probe` is the documented single verdict path.
    verdict = _probe(
        workspace,
        old=DELETE_QUOTING[0],
        new=DELETE_QUOTING[1],
        nodeid=SPACED,
        expect="",
    )
    assert verdict.name == mutations.STALE, verdict.detail


@pytest.mark.parametrize("generic", ["AssertionError:", "AssertionError", "Error", "ValueError: "])
def test_a_generic_expect_cannot_make_a_failure_caught(workspace: Path, generic: str):
    # The same hole as the empty expect, one step further along, and the only
    # degradation in this file's history that needs no code edit at all. Every
    # Python assertion failure's message begins with the exception class, so an
    # `expect` that is only that class matches whatever went wrong --
    # `"AssertionError:" in message` is true for the same structural reason
    # `"" in message` is.
    #
    # Measured before this guard: this fixture, whose entire job is to fail for
    # the *wrong* reason, came back CAUGHT for every string below, and so did
    # the source-echo fixture. Both canaries that carry the most weight passed
    # only because of the particular string they happened to pin, and the whole
    # of oracle 4 evaporated.
    #
    # `--emit-expect` is what makes this the likely mistake rather than an
    # exotic one: it prints the first line and says to include its prefix, and
    # the prefix is exactly this.
    verdict = _probe(
        workspace,
        old=DELETE_QUOTING[0],
        new=DELETE_QUOTING[1],
        nodeid="test_subject.py::test_that_goes_red_without_naming_the_reason",
        expect=generic,
    )
    assert verdict.name != mutations.CAUGHT, f"{generic!r} was accepted as evidence"


def test_an_expect_naming_an_observed_value_is_still_accepted():
    # The other side of the guard. Without this, "reject everything" would
    # satisfy the test above, and the table would be the thing that broke.
    for good in (
        "AssertionError: /home/me/my tbox/t.json",
        "import of pyrewire halted",
        "run --print-ontology to list the declared vocabulary",
        "how-it-works.md names --print-ontologyy, which the CLI does not accept",
    ):
        assert mutations.undiscriminating_expect(good) is None, good


def test_a_nodeid_naming_no_test_is_not_green(workspace: Path):
    # Measured on pytest 9: this exits 4 and writes a report with no
    # <testcase>, exactly as an unrecognised flag exits 4 and writes no report
    # at all. Anything reading the exit code calls both of them a caught
    # mutation. This canary is that failure, reproduced.
    verdict = _probe(
        workspace,
        old=DELETE_QUOTING[0],
        new=DELETE_QUOTING[1],
        nodeid="test_subject.py::test_no_such_test_exists",
        expect="spaced value must be quoted",
    )
    assert verdict.name == mutations.NO_SUCH_TEST, verdict.detail


def test_a_probe_restores_the_file_it_mutated(workspace: Path, monkeypatch):
    subject = workspace / "lib" / "subject.py"
    before = subject.read_bytes()

    # Watch the file *during* the probe rather than inferring from the verdict.
    # Asserting CAUGHT plus byte equality closes the case where `probe` stops
    # mutating and returns an honest verdict, but not the case where the
    # verdict is invented -- a `probe` returning CAUGHT as its first statement
    # satisfies both halves, one because it is fabricated and the other because
    # nothing was touched. Only an observation taken while the mutation should
    # be on disk can tell those apart.
    seen: list[bytes] = []
    real_run_node = mutations._run_node

    def watching(nodeid, cwd, env=None):
        seen.append(subject.read_bytes())
        return real_run_node(nodeid, cwd, env)

    monkeypatch.setattr(mutations, "_run_node", watching)

    verdict = _probe(
        workspace,
        old=DELETE_QUOTING[0],
        new=DELETE_QUOTING[1],
        nodeid=SPACED,
        expect="spaced value must be quoted",
    )
    assert verdict.name == mutations.CAUGHT, verdict.detail
    # The mutation was actually on disk while the test ran. This is the half a
    # verdict cannot supply, because a verdict can be fabricated.
    assert any(b"if False:" in payload for payload in seen), "the mutation was never on disk"
    # Bytes, not text: a text round-trip on Windows would rewrite line endings
    # and turn every restore into a diff that this assertion would miss.
    assert subject.read_bytes() == before


# --------------------------------------------------------------------------
# Oracle 3: the verdict comes from the test that was named.
#
# `probe` always invokes pytest with exactly one nodeid, so its report holds
# exactly one record and the identity filter is unobservable from any canary
# above -- dropping the `== nodeid` comparison entirely changed nothing they
# could see. These drive `read_report` against reports written here, which is
# the only way to hand it a report holding more than one record.
# --------------------------------------------------------------------------

TWO_RECORDS = """<?xml version="1.0" encoding="utf-8"?>
<testsuites><testsuite name="pytest" tests="2">
  <testcase classname="pkg.test_other" name="test_neighbour">
    <failure message="AssertionError: the neighbour failed">longrepr</failure>
  </testcase>
  <testcase classname="pkg.test_target" name="test_wanted" />
</testsuite></testsuites>
"""


def _written_report(tmp_path: Path, body: str) -> Path:
    path = tmp_path / "report.xml"
    path.write_text(body, encoding="utf-8")
    return path


def test_the_verdict_comes_from_the_named_record_not_the_first_one(tmp_path: Path):
    # The wanted test passed; a different test in the same report failed. A
    # reader that takes the first record, or any record, reports "failed" here
    # and would credit a mutation with a catch it never earned.
    result = mutations.read_report(
        _written_report(tmp_path, TWO_RECORDS), "pkg/test_target.py::test_wanted"
    )
    assert result.outcome == "passed", result.detail


def test_a_report_naming_only_other_tests_is_not_a_verdict(tmp_path: Path):
    result = mutations.read_report(
        _written_report(tmp_path, TWO_RECORDS), "pkg/test_absent.py::test_missing"
    )
    assert result.outcome == "missing", result.detail


DUPLICATE_RECORDS = """<?xml version="1.0" encoding="utf-8"?>
<testsuites><testsuite name="pytest" tests="2">
  <testcase classname="pkg.test_target" name="test_wanted">
    <failure message="AssertionError: the first copy failed">longrepr</failure>
  </testcase>
  <testcase classname="pkg.test_target" name="test_wanted" />
</testsuite></testsuites>
"""


def test_two_records_for_the_named_test_are_not_a_verdict(tmp_path: Path):
    # The other half of "exactly one match". Which record is the answer is
    # unknown, so there is no answer -- taking the first would grade a
    # mutation against whichever copy happened to be written first. Pinned
    # because relaxing the check to `< 1` left every other canary green.
    result = mutations.read_report(
        _written_report(tmp_path, DUPLICATE_RECORDS), "pkg/test_target.py::test_wanted"
    )
    assert result.outcome == "missing", result.detail


def test_a_report_that_was_never_written_is_not_a_verdict(tmp_path: Path):
    # The bad-flag shape: pytest dies in argument parsing and the report plugin
    # never runs. Measured to exit 4 -- the same code a nonexistent nodeid
    # exits -- which is why no exit code is read anywhere in the runner.
    result = mutations.read_report(tmp_path / "never-written.xml", "a.py::b")
    assert result.outcome == "missing", result.detail


# --------------------------------------------------------------------------
# The reporting layer: everything between a verdict and the number a human
# acts on.
#
# `probe` and `read_report` were hardened first and the canaries above cover
# them five ways. None of them touches this layer, and two independent gates
# found the same hole in it: a correct verdict thrown away on its way to
# stdout. Measured on the revision before this one -- dropping WRONG_REASON
# from UNEVALUABLE made a failed entry vanish and the run exit 0, and removing
# the survivor mapping made a SURVIVED entry exit 0, both with every canary
# above still green. `report_results` is a pure function, so these cost no
# subprocess and no fixture.
# --------------------------------------------------------------------------


def _verdict_row(name: str, verdict: str, test: str = "tests/test_x.py::test_y"):
    entry = mutations.Entry(
        name=name,
        target="src/agent_workflows_harness/cli.py",
        old="old",
        new="new",
        test=test,
        expect="AssertionError: something",
        note="a note",
    )
    return (entry, mutations.Verdict(verdict, "detail"))


def test_a_survivor_sets_the_exit_code_the_whole_file_exists_to_emit(capsys):
    # The docstring's stated purpose: a tripwire that stopped catching its
    # mutation says so. What it says with is this exit code.
    code = mutations.report_results([_verdict_row("a", mutations.SURVIVED)])
    assert code == mutations.EXIT_SURVIVED
    assert "1 survived" in capsys.readouterr().out


def test_an_unevaluable_entry_is_not_reported_as_caught(capsys):
    # WRONG_REASON specifically: it is the rarest verdict and the one added to
    # close an earlier finding, so its loss is the least likely to be noticed.
    code = mutations.report_results([_verdict_row("a", mutations.WRONG_REASON)])
    out = capsys.readouterr().out
    assert code == mutations.EXIT_UNEVALUABLE
    assert "0 caught" in out
    assert "1 unevaluable" in out


def test_an_all_caught_table_exits_zero_and_counts_honestly(capsys):
    code = mutations.report_results(
        [_verdict_row("a", mutations.CAUGHT), _verdict_row("b", mutations.CAUGHT)]
    )
    out = capsys.readouterr().out
    assert code == mutations.EXIT_OK
    assert "2 caught" in out
    assert "0 survived" in out


def test_every_verdict_the_runner_can_produce_lands_in_a_bucket(capsys):
    # The partition assertion, driven with every verdict name the runner
    # defines. A verdict in no bucket disappears from both the summary and the
    # exit code, which is exactly how the measured degradation stayed silent.
    every = [
        mutations.CAUGHT,
        mutations.SURVIVED,
        mutations.WRONG_REASON,
        mutations.ERRORED,
        mutations.STALE,
        mutations.AMBIGUOUS,
        mutations.NO_SUCH_TEST,
        mutations.BASELINE_RED,
        mutations.BROKEN,
    ]
    rows = [_verdict_row(f"e{index}", name) for index, name in enumerate(every)]
    code = mutations.report_results(rows)
    out = capsys.readouterr().out
    assert "runner bug" not in out, out
    assert code == mutations.EXIT_SURVIVED
    assert f"1 caught, 1 survived, {len(every) - 2} unevaluable" in out


def test_a_verdict_that_fits_no_bucket_is_a_runner_bug_not_a_green(capsys):
    code = mutations.report_results([_verdict_row("a", "SOME_NEW_VERDICT")])
    out = capsys.readouterr().out
    assert code != mutations.EXIT_OK
    assert "runner bug" in out


def test_the_summary_names_how_little_of_the_suite_the_table_covers(capsys):
    # A table pinning one test out of a hundred still prints a green. A reader
    # who takes that for a suite-wide result was misled by the shape of the
    # line, so the line states its own narrowness.
    mutations.report_results(
        [
            _verdict_row("a", mutations.CAUGHT, test="tests/test_x.py::test_one"),
            _verdict_row("b", mutations.CAUGHT, test="tests/test_x.py::test_one"),
        ],
        suite_size=124,
    )
    assert "2 entries covering 1 test of 124" in capsys.readouterr().out


def test_skipping_the_self_check_is_stated_in_the_summary(capsys):
    # Otherwise the only evidence is a missing line at the top of a run nobody
    # kept.
    mutations.report_results([_verdict_row("a", mutations.CAUGHT)], self_check_skipped=True)
    assert "--skip-self-check" in capsys.readouterr().out


def test_a_failing_precondition_stops_the_ones_after_it():
    # The gate ordering is the policy: an untrusted oracle must produce no
    # verdicts at all, so a failed self-check has to stop the run before the
    # table is graded rather than beside it. Inside `main` this was
    # unfalsifiable -- disabling the abort left every canary green.
    ran: list[str] = []

    def check(name: str, failure: str | None):
        def run() -> str | None:
            ran.append(name)
            return failure

        return run

    code, message = mutations.first_failing_precondition(
        [
            (mutations.EXIT_SELF_CHECK, check("first", None)),
            (mutations.EXIT_SELF_CHECK, check("oracle", "the oracle is not trustworthy")),
            (mutations.EXIT_UNEVALUABLE, check("suite", None)),
        ]
    )
    assert code == mutations.EXIT_SELF_CHECK
    assert message == "the oracle is not trustworthy"
    assert ran == ["first", "oracle"], "a later precondition ran after one had already failed"


def test_all_preconditions_passing_lets_the_run_proceed():
    code, message = mutations.first_failing_precondition(
        [(mutations.EXIT_SELF_CHECK, lambda: None), (mutations.EXIT_UNEVALUABLE, lambda: None)]
    )
    assert code is None and message == ""


def test_a_second_run_cannot_grade_the_same_tree(tmp_path: Path):
    # Two runners interleaving mutations restore each other's originals, and
    # the tree can end up holding an edit neither made.
    lock = tmp_path / mutations.LOCK_NAME
    with mutations._Lock(lock):
        with pytest.raises(mutations.LockHeld):
            with mutations._Lock(lock):
                pass
    assert not lock.exists(), "the lock outlived the run that held it"


def test_a_held_lock_does_not_report_itself_as_a_lost_tripwire():
    # Exit 1 means "a tripwire stopped catching its mutation", which is the
    # most consequential thing this runner says. A stale lock file must not be
    # able to impersonate it.
    assert mutations.EXIT_LOCKED != mutations.EXIT_SURVIVED
    assert mutations.EXIT_UNEXPECTED != mutations.EXIT_SURVIVED
    codes = [
        mutations.EXIT_OK,
        mutations.EXIT_SURVIVED,
        mutations.EXIT_UNEVALUABLE,
        mutations.EXIT_SELF_CHECK,
        mutations.EXIT_RESTORE_FAILED,
        mutations.EXIT_LOCKED,
        mutations.EXIT_UNEXPECTED,
    ]
    assert len(set(codes)) == len(codes), "two outcomes share an exit code"


def test_a_red_suite_is_reported_rather_than_graded(workspace: Path):
    # Oracle 5, outer half, driven against a real pytest run. The workspace
    # fixture carries a deliberately failing test, so a green answer here would
    # mean the check is not looking at anything.
    assert mutations._full_suite_is_green(workspace) is not None


def test_a_green_suite_lets_the_run_proceed(tmp_path: Path):
    (tmp_path / "test_fine.py").write_text("def test_fine():\n    assert True\n", encoding="utf-8")
    assert mutations._full_suite_is_green(tmp_path) is None


def test_a_restore_that_did_not_stick_is_reported_not_assumed(tmp_path: Path, monkeypatch):
    # The restore is verified byte for byte rather than assumed to have worked.
    # Deleting that comparison is invisible from every other canary, because
    # every other canary's restore succeeds.
    target = tmp_path / "subject.py"
    target.write_bytes(b"what is actually on disk")
    monkeypatch.setattr(mutations, "_write_atomic", lambda path, payload: None)
    with pytest.raises(mutations.RestoreFailed) as raised:
        mutations._restore(target, b"what the original was")
    # The message has to carry the recovery, because the reader is looking at
    # it while their working tree holds a mutation.
    assert "git checkout --" in str(raised.value)


def test_an_entry_whose_test_is_not_collected_is_refused_before_any_write(workspace: Path):
    # The preflight exists so a stale nodeid is found without touching the
    # tree. This entry names a target that does not exist, so if the preflight
    # were skipped the run would fail trying to read it -- which is the point:
    # nothing should get as far as opening a file.
    stale = mutations.Entry(
        name="stale",
        target="does/not/exist.py",
        old="old",
        new="new",
        test="test_subject.py::test_deleted_last_year",
        expect="AssertionError: something",
        note="a note",
    )
    results = mutations.run_table([stale], collected={SPACED}, root=workspace)
    assert [verdict.name for _, verdict in results] == [mutations.NO_SUCH_TEST]


def _workspace_entry(workspace: Path, **overrides) -> "object":
    defaults = dict(
        name="canary",
        target="lib/subject.py",
        old=DELETE_QUOTING[0],
        new=DELETE_QUOTING[1],
        test=SPACED,
        expect="spaced value must be quoted",
        note="a note",
        module="subject",
        path_entry="lib",
    )
    defaults.update(overrides)
    return mutations.Entry(**defaults)


def test_a_table_entry_reaches_the_import_oracle(workspace: Path):
    # The wire, not the oracle. Oracle 1 is pinned five ways, but every one of
    # those canaries passes `importable` explicitly, so `_importable_for`
    # returning None would silently disable the import check for *every real
    # entry* while all of them stayed green -- and a syntax-error mutation
    # would then be graded instead of reported BROKEN.
    entry = _workspace_entry(workspace, old="return value", new="return value +")
    results = mutations.run_table([entry], collected={SPACED}, root=workspace)
    assert [verdict.name for _, verdict in results] == [mutations.BROKEN], results[0][1].detail


def test_a_table_entry_reaches_the_verdict_path_at_all(workspace: Path):
    entry = _workspace_entry(workspace)
    results = mutations.run_table([entry], collected={SPACED}, root=workspace)
    assert [verdict.name for _, verdict in results] == [mutations.CAUGHT], results[0][1].detail


def test_the_authoring_path_recommends_a_pin_that_can_discriminate(workspace: Path, capsys):
    # The authoring path is the only layer where being wrong is self-sealing:
    # a bad pin is handed to the author, pasted in good faith, and then every
    # oracle downstream agrees with it. Nothing tested it at all.
    entry = _workspace_entry(workspace)
    code = mutations.emit_expect(entry, root=workspace)
    printed = capsys.readouterr().out
    assert code == mutations.EXIT_OK, printed

    # Isolate the line the author is told to paste. Asserting only that the
    # right text appears *somewhere* in the output is satisfied by the full
    # message printed below it, so it would not notice the recommended line
    # itself being wrong -- which is the whole failure mode here.
    lines = printed.splitlines()
    label = next(i for i, line in enumerate(lines) if "paste this first line" in line)
    recommended = lines[label + 1]
    assert recommended.startswith("AssertionError: "), recommended
    assert "spaced value must be quoted" in recommended, recommended

    pin = mutations.recommended_pin("AssertionError: spaced value must be quoted\nassert (False)")
    assert pin == "AssertionError: spaced value must be quoted"
    # What it recommends must survive the guard it will be checked against,
    # and must not be line 2 -- `assert (False)` carries no prefix and is
    # satisfiable by an enormous class of unrelated failures.
    assert mutations.undiscriminating_expect(pin) is None
    assert pin != "assert (False)"
    assert "spaced value must be quoted" in printed, printed
    # And the failing location, so the author can see *where* it broke.
    assert "test_subject.py:" in printed, printed


def test_the_authoring_path_refuses_an_anchor_that_is_not_unique(workspace: Path, capsys):
    # Same rule as the table's, at the point where an entry is written. An
    # author pinning from an ambiguous anchor gets a message produced by
    # mutating every site at once, which describes no entry they could write.
    entry = _workspace_entry(workspace, old="value", new="valu3")
    code = mutations.emit_expect(entry, root=workspace)
    assert code != mutations.EXIT_OK
    assert "exactly once" in capsys.readouterr().out


def test_the_authoring_path_refuses_a_test_that_is_already_red(workspace: Path, capsys):
    entry = _workspace_entry(
        workspace, test="test_subject.py::test_that_is_already_red_before_any_mutation"
    )
    code = mutations.emit_expect(entry, root=workspace)
    assert code != mutations.EXIT_OK
    assert "does not pass on the clean tree" in capsys.readouterr().out


def test_a_red_self_check_is_reported_rather_than_ignored(workspace: Path):
    # The gate ordering was extracted and pinned; this is the check itself.
    # Making `_self_check` return None unconditionally left every canary green,
    # so a red oracle would have aborted nothing -- falsifiable ordering,
    # unfalsifiable content, and I reported it as closed.
    failure = mutations._self_check(False, cwd=workspace, target="test_subject.py")
    assert failure is not None and "not trustworthy" in failure


def test_a_green_self_check_lets_the_run_proceed(tmp_path: Path):
    (tmp_path / "test_ok.py").write_text("def test_ok():\n    assert True\n", encoding="utf-8")
    assert mutations._self_check(False, cwd=tmp_path, target="test_ok.py") is None


def test_skipping_the_self_check_returns_no_failure(tmp_path: Path):
    assert mutations._self_check(True, cwd=tmp_path, target="nonexistent.py") is None


def test_the_import_rule_refuses_an_entry_naming_a_module_that_is_not_there():
    stray = mutations.Entry(
        name="stray",
        target="src/agent_workflows_harness/cli.py",
        old="old",
        new="new",
        test="tests/test_x.py::test_y",
        expect="AssertionError: something",
        note="a note",
        module="agent_workflows_harness.no_such_module",
    )
    drift = mutations.verify_import_rule([stray])
    assert drift is not None and "no_such_module" in drift


def test_the_import_rule_refuses_an_entry_whose_module_and_target_disagree():
    # The guard has two branches and only one was pinned. This is the other,
    # and it is the one implementing the function's stated purpose: both files
    # exist, so `not landing.exists()` does not fire, and the mismatch check
    # is all that stands between an entry mutating one file and import-checking
    # another. Replacing it with `if False:` left every canary green.
    crossed = mutations.Entry(
        name="crossed",
        target="src/agent_workflows_harness/cli.py",
        old="old",
        new="new",
        test="tests/test_x.py::test_y",
        expect="AssertionError: something",
        note="a note",
        module="agent_workflows_harness.selector",
    )
    drift = mutations.verify_import_rule([crossed])
    assert drift is not None, "an entry naming two different files was accepted"
    assert "selector" in drift and "cli.py" in drift, drift


def test_the_import_rule_passes_for_the_shipped_table():
    assert mutations.verify_import_rule(mutations.load_table()) is None


def test_a_mutation_is_never_written_straight_onto_the_target(tmp_path: Path, monkeypatch):
    # Oracle 6. Both the mutation and the restore stage a sibling file and
    # `os.replace` it into position, so an interrupted write cannot truncate
    # the source. Nothing observed that: writing directly with `write_bytes`
    # left every canary green.
    #
    # Falsified by making the replace step fail. If the staging path is in use
    # the target still holds its original bytes; a direct write would already
    # have overwritten them.
    target = tmp_path / "subject.py"
    target.write_bytes(b"the original bytes")

    def refuse(src, dst):
        raise OSError("replace refused")

    monkeypatch.setattr(mutations.os, "replace", refuse)
    with pytest.raises(OSError):
        mutations._write_atomic(target, b"the mutated bytes")
    assert target.read_bytes() == b"the original bytes"
    # And the staging file is cleaned up rather than left inside the package.
    assert not list(tmp_path.glob(f"{mutations.STAGING_PREFIX}*"))


# --------------------------------------------------------------------------
# `main` itself: the wiring.
#
# Four rounds of review found four frontiers -- `probe`, the reporting layer,
# the authoring path, and this one -- and each was exactly what the self-check
# did not call. Six separate degradations of `main` left all sixty canaries
# green, including re-losing the import check on the authoring path, which by
# then had been lost twice and restored with a comment describing both losses.
# A comment is what failed the first two times.
# --------------------------------------------------------------------------


@pytest.fixture
def gradable(tmp_path: Path) -> Path:
    """A tiny repo `main` can grade end to end: green suite, one real entry."""

    (tmp_path / "lib").mkdir()
    (tmp_path / "lib" / "subject.py").write_text(SUBJECT, encoding="utf-8")
    (tmp_path / "test_only.py").write_text(
        "from subject import quote\n\n\n"
        "def test_a_spaced_value_is_quoted():\n"
        "    assert quote('a b') == '\"a b\"', 'spaced value must be quoted'\n",
        encoding="utf-8",
    )
    (tmp_path / "pytest.ini").write_text("[pytest]\npythonpath = lib\n", encoding="utf-8")
    return tmp_path


def _gradable_entry(**overrides):
    defaults = dict(
        name="canary",
        target="lib/subject.py",
        old=DELETE_QUOTING[0],
        new=DELETE_QUOTING[1],
        test="test_only.py::test_a_spaced_value_is_quoted",
        expect="AssertionError: spaced value must be quoted",
        note="a note",
        module="subject",
        path_entry="lib",
    )
    defaults.update(overrides)
    return mutations.Entry(**defaults)


def test_main_grades_a_table_end_to_end(gradable: Path, capsys):
    code = mutations.main(["--skip-self-check"], root=gradable, entries=[_gradable_entry()])
    out = capsys.readouterr().out
    assert code == mutations.EXIT_OK, out
    assert "CAUGHT" in out


def test_the_summary_counts_the_suite_it_actually_collected(gradable: Path, capsys):
    # The denominator. `docs/maintenance.md` tells a reader to know what the
    # green covers before trusting it, and points at this line -- so the half
    # they calibrate against must not be able to lie. Degrading the collection
    # parse changed 156 to 33 with no other symptom.
    mutations.main(["--skip-self-check"], root=gradable, entries=[_gradable_entry()])
    out = capsys.readouterr().out
    collected = mutations._collected_node_ids(gradable)
    assert collected, "the fixture collected nothing, so the assertion below proves nothing"
    assert f"of {len(collected)}" in out, out


def test_the_authoring_path_still_verifies_the_import_rule(gradable: Path, capsys):
    # H1. The check has been lost twice and restored once with only a comment
    # holding it. Moving it back below the --emit-expect branch is invisible to
    # every other canary, so this is the one that has to notice.
    stray = _gradable_entry(module="no_such_module_anywhere")
    code = mutations.main(["--emit-expect", "canary"], root=gradable, entries=[stray])
    assert code == mutations.EXIT_SELF_CHECK, capsys.readouterr().out


def test_the_authoring_path_names_the_entry_it_ran(gradable: Path, capsys):
    # A `find_entry` returning the wrong entry would otherwise print another
    # entry's pin with nothing identifying the substitution.
    mutations.main(["--emit-expect", "canary"], root=gradable, entries=[_gradable_entry()])
    assert "entry: canary" in capsys.readouterr().out


def test_main_refuses_a_name_no_entry_carries(gradable: Path, capsys):
    code = mutations.main(["--emit-expect", "nope"], root=gradable, entries=[_gradable_entry()])
    assert code == mutations.EXIT_UNEVALUABLE
    assert "no entry named" in capsys.readouterr().out


def test_main_refuses_to_grade_against_a_red_suite(workspace: Path, capsys):
    # The `workspace` fixture carries a deliberately failing test, so a run
    # that graded anything here would be grading against a red baseline.
    code = mutations.main(["--skip-self-check"], root=workspace, entries=[])
    assert code == mutations.EXIT_UNEVALUABLE
    assert "not green" in capsys.readouterr().out


def test_main_refuses_to_grade_when_it_cannot_enumerate_the_suite(
    gradable: Path, capsys, monkeypatch
):
    # H3. The preflight's haystack. An empty `collected` cannot be produced by
    # any natural fixture -- a root with no tests is caught one gate earlier by
    # the suite check, with the same exit code -- so the guard is driven
    # directly. Without it the preflight silently matches nothing and every
    # entry reads NO_SUCH_TEST.
    monkeypatch.setattr(mutations, "_collected_node_ids", lambda root: set())
    code = mutations.main(["--skip-self-check"], root=gradable, entries=[_gradable_entry()])
    assert code == mutations.EXIT_UNEVALUABLE
    assert "refusing to grade blind" in capsys.readouterr().out


def test_a_crash_in_the_reporting_layer_cannot_look_like_a_lost_tripwire(
    gradable: Path, capsys, monkeypatch
):
    # `EXIT_SURVIVED` is 1, and an exception escaping main exits 1 too. The
    # crash guard exists for exactly that, and the reporting layer -- the
    # newest layer, added because it was found unvalidated -- was the one call
    # sitting outside it.
    def explode(*args, **kwargs):
        raise RuntimeError("the reporter fell over")

    monkeypatch.setattr(mutations, "report_results", explode)
    code = mutations.main(["--skip-self-check"], root=gradable, entries=[_gradable_entry()])
    assert code == mutations.EXIT_UNEXPECTED, capsys.readouterr().out
    assert code != mutations.EXIT_SURVIVED


def test_a_failed_restore_while_authoring_is_reported_as_a_dirty_tree(
    gradable: Path, capsys, monkeypatch
):
    # A RestoreFailed raised from emit_expect used to fall through to the crash
    # handler, so a tree verified to be dirty was reported as an unexplained
    # failure rather than as the one condition with a recovery command.
    def refuse(path, original):
        raise mutations.RestoreFailed(f"{path} was not restored. Recover with: git checkout --")

    monkeypatch.setattr(mutations, "_restore", refuse)
    code = mutations.main(["--emit-expect", "canary"], root=gradable, entries=[_gradable_entry()])
    out = capsys.readouterr().out
    assert code == mutations.EXIT_RESTORE_FAILED, out
    # The recovery command has to survive the routing, since the reader is
    # looking at this while their tree holds a mutation.
    assert "git checkout --" in out


def test_main_runs_the_self_check_unless_told_not_to(gradable: Path, capsys):
    # H6. `--skip-self-check` defaulting to on would mean the oracle is never
    # validated, and nothing else would say so. Without the flag, `_self_check`
    # looks for tests/test_mutations.py in the root, which this fixture does
    # not have, so the run must stop rather than grade.
    code = mutations.main([], root=gradable, entries=[_gradable_entry()])
    assert code == mutations.EXIT_SELF_CHECK, capsys.readouterr().out


# --------------------------------------------------------------------------
# Table lint. No subprocesses, no writes -- these are cheap enough to sit in
# the gate, and they catch the entry defects that would otherwise only surface
# when someone remembers to run the runner.
# --------------------------------------------------------------------------


def test_every_entry_is_complete_and_distinct():
    table = mutations.load_table()
    assert table, "the table is empty, so every assertion below is vacuous"
    names = [item.name for item in table]
    assert len(names) == len(set(names)), "two entries share a name"
    seen = set()
    for item in table:
        assert item.old, f"{item.name} has no anchor"
        assert item.new, f"{item.name} has no replacement"
        assert item.old != item.new, f"{item.name} mutates nothing"
        assert item.expect, f"{item.name} pins no failure message"
        assert item.note, f"{item.name} does not say why the behaviour matters"
        assert "::" in item.test, f"{item.name} does not name a pytest nodeid"
        assert mutations.undiscriminating_expect(item.expect) is None, (
            f"{item.name}: {mutations.undiscriminating_expect(item.expect)}"
        )
        key = (item.target, item.old, item.new)
        assert key not in seen, f"{item.name} duplicates another entry's mutation"
        seen.add(key)
    # Two entries pinning the same string are two entries that cannot tell
    # their own failures apart -- the shape that made the first two entries
    # mutually satisfiable before `expect` moved to the message attribute.
    pins = [item.expect for item in table]
    assert len(pins) == len(set(pins)), "two entries pin the same failure message"


def test_no_anchor_spans_more_than_one_line():
    # `core.autocrlf` is true here and the working copy is entirely CRLF, so an
    # anchor written with a bare "\n" would never match and the entry would
    # report STALE on Windows and CAUGHT on POSIX. Loud, but loud about the
    # wrong thing. Normalising line endings for the match is not the fix: the
    # restore is verified byte for byte and must stay that way. Single-line
    # anchors sidestep it entirely and are more precise anyway.
    for item in mutations.load_table():
        assert "\n" not in item.old, f"{item.name}'s anchor spans lines"
        assert "\r" not in item.old, f"{item.name}'s anchor carries a line ending"
        assert "\n" not in item.new, f"{item.name}'s replacement spans lines"


def test_no_entry_pins_a_memory_address():
    # A repr like `<built-in method startswith of str object at 0x...>` appears
    # in these payloads, and the address changes every run. Both hex cases: the
    # real repr is uppercase, and a lowercase-only class matched it only by the
    # accident of its leading zeros.
    assert mutations.ADDRESS_PATTERN.search("0x1A2B3C4D"), "the guard cannot see uppercase hex"
    for item in mutations.load_table():
        assert not mutations.ADDRESS_PATTERN.search(item.expect), (
            f"{item.name} pins a memory address, which changes every run"
        )


def test_every_anchor_appears_exactly_once_in_its_target():
    # A stale anchor is reported as STALE rather than green by the runner, but
    # only when someone runs it. This is the same check in the gate, where it
    # costs nothing.
    for item in mutations.load_table():
        target = ROOT / item.target
        assert target.exists(), f"{item.name} targets {item.target}, which does not exist"
        found = target.read_text(encoding="utf-8").count(item.old)
        assert found == 1, f"{item.name}: anchor appears {found} times in {item.target}"


def test_every_entry_names_a_test_that_exists():
    for item in mutations.load_table():
        relative, _, test_name = item.test.partition("::")
        source = ROOT / relative
        assert source.exists(), f"{item.name} names {relative}, which does not exist"
        assert f"def {test_name}(" in source.read_text(encoding="utf-8"), (
            f"{item.name} names {test_name}, which {relative} does not define"
        )


def test_no_two_test_files_share_a_bare_test_name():
    # Hygiene, not a protective control, and the difference is worth stating
    # because an earlier version of this comment claimed the latter. `_node_id`
    # namespaces by `classname`, so two files sharing a bare name produce two
    # distinct nodeids and the runner is not confused by them at all. What this
    # buys is only that a human reading a verdict line can tell which test it
    # names without checking the file.
    # Parsed, not grepped. A `^def test_` regex also harvests the fixture test
    # names out of this file's own TEST_SUBJECT literal, so it reported names
    # that exist only inside a string and could raise a collision against one.
    by_name: dict[str, list[str]] = {}
    for source in sorted(ROOT.glob("tests/test_*.py")):
        tree = ast.parse(source.read_text(encoding="utf-8"))
        for node in tree.body:
            if isinstance(node, ast.FunctionDef) and node.name.startswith("test_"):
                by_name.setdefault(node.name, []).append(source.name)
    collisions = {name: files for name, files in by_name.items() if len(files) > 1}
    assert by_name, "no test names were found, so this assertion proves nothing"
    assert not collisions, f"bare test names collide across files: {collisions}"


def test_the_suite_mutates_the_source_tree_it_imports():
    # `pytest.ini` sets `pythonpath = src`, so the suite imports `src/` no
    # matter how the package is installed. That is the invariant the whole
    # table rests on: if anything ever shadowed it, every entry would mutate a
    # file nobody runs and come back SURVIVED -- loud, but wrong about the
    # tests rather than about the tree. This pins the setting itself.
    ini = (ROOT / "pytest.ini").read_text(encoding="utf-8")
    assert "pythonpath = src" in ini, "the suite no longer pins which tree it imports"
    import agent_workflows_harness.cli as under_test

    expected = (ROOT / "src" / "agent_workflows_harness" / "cli.py").resolve()
    assert Path(under_test.__file__).resolve() == expected

    # A second observer, by a different mechanism. `verify_import_rule` used to
    # carry the environmental half of this and no longer can -- both of its
    # sides now come from an entry's own fields, so it cannot see a
    # non-editable install shadowing `src/`. That left this the only test
    # holding an invariant the whole table rests on, and a lone observer is the
    # thing this file refuses everywhere else. This one asks a fresh
    # interpreter under the runner's own PYTHONPATH rule, so it fails for
    # reasons the in-process import above cannot.
    resolved = subprocess.run(
        [sys.executable, "-c", "import agent_workflows_harness.cli as m; print(m.__file__)"],
        cwd=str(ROOT),
        env={**os.environ, "PYTHONPATH": str(ROOT / "src")},
        capture_output=True,
        text=True,
    )
    assert resolved.returncode == 0, resolved.stderr
    assert Path(resolved.stdout.strip()).resolve() == expected, resolved.stdout


def test_the_runner_is_not_collected_by_the_suite():
    # The table writes to `src/` mid-run, so an interrupted suite would leave a
    # mutated source file on disk. That is the whole reason, and it is enough:
    # "the gate would run pytest inside pytest" is not a second reason, because
    # this file already spawns pytest subprocesses by the dozen.
    assert not (ROOT / "tests" / "mutations.py").name.startswith("test_")
    collected = {path.name for path in ROOT.glob("tests/test_*.py")}
    assert "mutations.py" not in collected


def test_the_module_docstring_tells_a_reader_how_to_run_it():
    # The runner is the mechanism and nothing runs it automatically, so the
    # invocation has to be findable from the file itself.
    doc = mutations.__doc__ or ""
    assert textwrap.dedent(doc).strip(), "the runner lost its docstring"
    assert "tests/mutations.py" in doc
    assert "--emit-expect" in doc


def test_the_checklist_the_runner_claims_to_be_listed_in_lists_it():
    # The runner's docstring points at this checklist as the one thing that
    # causes it to be run, since there is no CI. That sentence was written
    # before the bullet existed, which is the same defect the runner exists to
    # catch: a stated control that was not built. Pinned so the claim and the
    # thing it claims cannot drift apart again.
    doc = mutations.__doc__ or ""
    assert "docs/maintenance.md" in doc, "the runner no longer names a checklist"
    checklist = (ROOT / "docs" / "maintenance.md").read_text(encoding="utf-8")
    assert "tests/mutations.py" in checklist, (
        "the runner says it is listed under Validation, and it is not"
    )
    validation = checklist.split("## Validation", 1)
    assert len(validation) == 2, "maintenance.md no longer has a Validation section"
    assert "tests/mutations.py" in validation[1], "the entry is not under Validation"


def test_the_checklist_states_how_little_the_table_covers():
    # The summary line names its own narrowness, but only for someone who runs
    # a 26-second runner. This puts the same figure where it is read *before*
    # deciding whether the green is worth having, and pins it so it cannot go
    # stale: growing the table forces the checklist to be edited with it.
    #
    # Deliberately not a test that fails while a gap is open. A test red by
    # design, in a repo with no CI, is a red a developer learns to route
    # around -- and it would be the only red in an otherwise green suite,
    # which is the exact condition under which a specific failure gets
    # ignored. Visibility, not failure.
    table = mutations.load_table()
    covered = len({item.test for item in table})
    checklist = (ROOT / "docs" / "maintenance.md").read_text(encoding="utf-8")
    claim = f"**{len(table)} entries covering {covered} test"
    assert claim in checklist, (
        f"the checklist does not state the table's real coverage; expected {claim!r}"
    )


def test_the_watched_set_is_empty_without_a_table(monkeypatch):
    # The falsifier for the guard above. Without it, the guard is a claim about
    # the derivation that nothing checks -- which is what it was: the constant
    # was appended first, so a derivation returning nothing still passed.
    monkeypatch.setattr(mutations, "load_table", list)
    with pytest.raises(AssertionError, match="no targets derived"):
        watched_targets()


def test_the_watched_set_covers_every_file_the_table_can_mutate():
    watched = set(watched_targets())
    for item in mutations.load_table():
        assert ROOT / item.target in watched, f"{item.name}'s target is not watched"
    assert ROOT / "src" / "agent_workflows_harness" / "cli.py" in watched


def test_the_lock_file_the_runner_creates_is_ignored():
    # A killed run leaves it behind. Untracked and unignored, it makes
    # `git status` dirty and reads as a stray file nobody can place.
    ignored = (ROOT / ".gitignore").read_text(encoding="utf-8")
    assert mutations.LOCK_NAME in ignored, "the lock would show up as an untracked file"
    # The staging file is the one that matters: `_write_atomic` creates it
    # inside the directory being mutated, so a hard kill between mkstemp and
    # os.replace leaves it in `src/`, beside the package's own sources.
    assert f"{mutations.STAGING_PREFIX}*" in ignored, (
        "a killed run would leave an untracked staging file inside src/"
    )
