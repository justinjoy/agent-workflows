"""A checked-in mutation table, so a tripwire that stops catching its mutation says so.

Run it:

    .venv/Scripts/python.exe tests/mutations.py        # Windows
    .venv/bin/python tests/mutations.py                # POSIX

Not collected by pytest: the filename matches neither `test_*.py` nor
`*_test.py`. Only the self-check in `tests/test_mutations.py` runs in the gate,
because this file writes to `src/` mid-run and a suite interrupted with `-x`
would leave a mutated source file on disk. The cost of that choice is real and
worth stating: nothing runs this automatically, because this repo has no CI. It
is listed in `docs/maintenance.md` under Validation, which is the checklist that
does exist.

Why this exists
---------------

Eleven assertions in one change (issue #11) passed while the behaviour they
named was deleted. None was found by reading. Every one was found by deleting
the behaviour and watching the suite stay green. The rule that covers them is
recorded at the top of `tests/test_plugin_package.py`:

    a presence assertion is only as strong as the proof that its haystack would
    fail if the behaviour under test were deleted, and the proof is deleting it.

Writing that rule down did not prevent the next instance -- one shipped inside
the commit series that checked the rule in. So this is the mechanism rather than
a second copy of the rule. It inverts the failure mode: today a tripwire that
quietly stops catching its mutation is silent, and here that entry goes
SURVIVED and the runner exits non-zero.

Why the runner is not trusted either
------------------------------------

Three separate people produced a *broken* mutation runner while hunting this
exact defect class, and each one read as "all caught". A green line from this
file is a claim that a tripwire failed to fire, and a green line produced by a
broken mutation is indistinguishable from one produced by a vacuous assertion.
So every verdict comes from an oracle that cannot be faked by the failure modes
that actually happened:

1. The mutated file must still import. A syntax error is a mutation that did
   not happen, not a tripwire that failed. -> BROKEN, never CAUGHT.
2. The mutation must have applied, at exactly one site. Anchor missing is
   STALE; anchor ambiguous is AMBIGUOUS. Neither is ever a green.
3. The verdict is read from the named test's own `<testcase>` record in a JUnit
   report. **The pytest exit code is never read.** Measured: a bad flag and a
   nonexistent nodeid both exit 4, so the exit code cannot separate "the
   tripwire fired" from "the invocation was broken" -- that is exactly how one
   of the three broken runners reported 21 of 21 mutations as caught. A bad
   flag writes no report at all; a bad nodeid writes one with no `<testcase>`.
   Both are distinguishable from a `<failure>`, and only by looking there.
4. `expect` is matched against the `<failure>` element's **`message`
   attribute**, never its text. The text is pytest's full longrepr, which
   echoes every source line of the test function from its `def` down to the
   failing line -- so a substring found there may simply be a literal the test
   file contains, which is issue #12's group A exactly. Measured on the two
   entries below: the bare fixture literal `/home/me/my tbox/t.json` appears in
   the longrepr of *either* entry's mutation, because both fixtures live in one
   tuple above every assertion in that test, so pinning a bare literal would
   not discriminate between them.

   Two things stop that here, and they are independent, so neither is the whole
   story:

   - the element choice, pinned by
     `test_a_failure_whose_source_echoes_another_expect_is_not_caught` in the
     self-check, which fails if this match ever moves to the longrepr;
   - the `AssertionError: ` prefix every captured `expect` carries, which a
     source echo never has. This is why `--emit-expect` prints the message
     attribute for pasting rather than telling an author to find a distinctive
     line in the output themselves.

   An author who pastes a fragment without that prefix still has the first
   guard. An author who keeps the prefix still has the second. Do not remove
   either on the grounds that the other covers it.
5. The baseline is verified, not assumed: the full suite must be green at
   startup, and each entry's named test must pass on the clean tree before it
   is mutated.
6. The restore is verified byte for byte, and both the mutation and the restore
   go through `os.replace`, which is atomic on NTFS and POSIX alike. A write
   interrupted mid-flight would otherwise leave the source truncated, which is
   a worse state than the mutation.

And the runner's own oracle is validated rather than asserted: see
`tests/test_mutations.py`, which drives `probe()` -- this file's only verdict
path, and the table's only caller -- against generated fixtures whose correct
verdict is known, including a deliberately vacuous test that MUST come back
SURVIVED and a test that fails for the wrong reason that MUST come back
WRONG_REASON. A runner that reports everything as caught fails that gate.

Adding an entry
---------------

1. Write the mutation as an exact `old` -> `new` substring pair. `old` must
   appear exactly once in the target file, and must not span lines: this repo
   checks out CRLF, so an anchor written with a bare "\\n" would silently never
   match here while matching fine on POSIX. The table lint rejects one.
2. Name the test that should catch it, as a full pytest nodeid.
3. Run `python tests/mutations.py --emit-expect <name>` and paste the printed
   `message` line into `expect`. **Never guess it.** A guessed `expect` is an
   assertion about what you believe the failure says, which is the shape of
   defect this file exists to catch.
4. Keep `expect` free of memory addresses; the table lint rejects them, because
   an address changes every run.

A non-Python target (a document, a manifest) is allowed: leave `module` unset
and oracle 1 is skipped for that entry, since "it still imports" means nothing
about Markdown. The other five apply unchanged. No table entry uses this yet --
`test_a_target_that_is_not_python_skips_only_the_import_oracle` in the
self-check is what keeps the path live -- and the first one that should is the
doc fence scan, for the reason in the next paragraph.

What this seed does not cover yet
---------------------------------

Two entries, both from the issue's later comment, both in `cli.py`. Named
plainly because a thin seed is a defensible first increment and an
overstated one is not:

- The **doc fence scan** (`test_every_flag_the_documents_name_is_a_flag_the_cli_accepts`)
  is the largest single cluster in the issue's evidence -- one site, three
  separate regex defects, each of which emptied the captured block list so
  every per-item assertion inside the loop was vacuously satisfied. It mutates
  `docs/how-it-works.md`, so it is the `module=None` case above.
- The **rejection hint** and the **runtime-independence branch**, the other two
  mutations the issue's body names by test.

None of the three is here yet. The mechanism is what commit one is for; an
entry is data, and data that has not been observed red is a guess.
"""

from __future__ import annotations

import argparse
import os
import re
import shutil
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
# The interpreter running this file. Never a bare "python": the project venv is
# the only environment where the suite is green, and resolving through PATH is
# how a run silently grades a different installation.
PYTHON = sys.executable

# Only CAUGHT is green. Every other verdict is a reason the entry could not be
# shown to work, and they are distinct because their remedies are distinct: a
# STALE entry means the table needs updating, a SURVIVED entry means a test
# needs fixing, and reporting either as the other wastes the run.
CAUGHT = "CAUGHT"
SURVIVED = "SURVIVED"
WRONG_REASON = "WRONG_REASON"
ERRORED = "ERRORED"
STALE = "STALE"
AMBIGUOUS = "AMBIGUOUS"
NO_SUCH_TEST = "NO_SUCH_TEST"
BASELINE_RED = "BASELINE_RED"
BROKEN = "BROKEN"

# Verdicts that mean "the table could not evaluate this entry", as opposed to
# SURVIVED, which is an evaluated entry with a bad answer. Kept as one set so
# the exit-code mapping and the summary line cannot disagree about which is
# which.
UNEVALUABLE = frozenset(
    {WRONG_REASON, ERRORED, STALE, AMBIGUOUS, NO_SUCH_TEST, BASELINE_RED, BROKEN}
)

EXIT_OK = 0
EXIT_SURVIVED = 1
EXIT_UNEVALUABLE = 2
EXIT_SELF_CHECK = 3
EXIT_RESTORE_FAILED = 4
# A held lock and an unexpected crash used to land on 1, which is the code for
# "a tripwire stopped catching its mutation" -- the most consequential thing
# this runner says. A stale lock file reading as a lost tripwire is a lie about
# the one message that must not be wrong, so both get their own code.
EXIT_LOCKED = 5
EXIT_UNEXPECTED = 6

# A memory address in an `expect` would flap every run, because the allocator
# hands back a different one. Both hex cases: CPython prints these uppercase
# (`0x0000016F88C02DF0`), and a lowercase-only class matched that string only by
# accident of its leading zeros.
ADDRESS_PATTERN = re.compile(r"0x[0-9a-fA-F]{6,}")
# A bare word after the exception class is a class name, not evidence about
# behaviour. See `undiscriminating_expect`.
_BARE_WORD = re.compile(r"^\w+$")

# The two things a killed run can leave behind, both ignored rather than
# showing up as stray untracked files nobody can place. The staging file is the
# one that matters: it lands inside `src/`, next to the file being mutated.
LOCK_NAME = ".mutations.lock"
STAGING_PREFIX = ".mutations-"


@dataclass(frozen=True)
class Verdict:
    """One entry's outcome, plus why. `detail` is printed in the footer."""

    name: str
    detail: str = ""

    @property
    def ok(self) -> bool:
        return self.name == CAUGHT


@dataclass(frozen=True)
class Entry:
    """One mutation and the tripwire that must catch it.

    `target` is repo-relative and POSIX-separated so the table carries no
    platform in it. `module` is the dotted name to import-check; leave it unset
    for a target that is not importable Python, which skips oracle 1 alone.
    """

    name: str
    target: str
    old: str
    new: str
    test: str
    expect: str
    note: str
    module: str | None = None
    # Repo-relative directory that must be on `sys.path` for `module` to
    # resolve. Matches `pythonpath = src` in pytest.ini; a field rather than a
    # constant so the self-check can drive the real wiring against a fixture.
    path_entry: str = "src"


@dataclass
class NodeResult:
    """What a single pytest node did, read from its JUnit record.

    `outcome` is one of passed / failed / errored / missing. `missing` covers
    both "pytest wrote no report" and "the report named no such test", which
    are the two shapes a broken invocation takes; neither is ever read as a
    test result.
    """

    outcome: str
    message: str = ""
    detail: str = ""


def _node_id(case: ET.Element) -> str:
    """Rebuild a pytest nodeid from a JUnit `<testcase>`.

    JUnit records `classname="tests.test_ontology"` and `name="test_x"`; pytest
    addresses the same test as `tests/test_ontology.py::test_x`. Comparing the
    rebuilt id against the requested one is what makes the verdict come from
    the test that was named rather than from whatever happened to run.
    """

    classname = case.get("classname", "")
    name = case.get("name", "")
    if not classname:
        return name
    return classname.replace(".", "/") + ".py::" + name


def _run_node(nodeid: str, cwd: Path, env: dict[str, str] | None = None) -> NodeResult:
    """Run one pytest node and read its verdict from the JUnit report.

    The subprocess exit code is deliberately never consulted. Measured on
    pytest 9.1.1: an unrecognised flag and a nonexistent nodeid both exit 4,
    the first writing no report and the second writing one with no `<testcase>`.
    An exit code therefore cannot tell a fired tripwire from a broken
    invocation, and reading it as one is how a mutation runner reports every
    mutation as caught.
    """

    workdir = tempfile.mkdtemp(prefix="mutations-junit-")
    report = Path(workdir) / "result.xml"
    try:
        subprocess.run(
            [
                PYTHON,
                "-m",
                "pytest",
                "-q",
                "-p",
                "no:cacheprovider",
                "--junit-xml",
                str(report),
                nodeid,
            ],
            cwd=str(cwd),
            env=env,
            capture_output=True,
            text=True,
        )
        return read_report(report, nodeid)
    finally:
        shutil.rmtree(workdir, ignore_errors=True)


def read_report(report: Path, nodeid: str) -> NodeResult:
    """Read one named test's outcome out of a JUnit report.

    Split out of `_run_node` so the self-check can drive it against a report it
    wrote by hand. Without that, the identity filter below is unexercised: a
    canary that runs one nodeid gets a one-record report either way, so
    dropping the `== nodeid` comparison changes nothing it can observe. The
    filter is oracle 3 -- the verdict must come from the test that was named,
    not from whatever happened to run -- and a guarantee nothing can falsify is
    not a guarantee.
    """

    if not report.exists():
        # A usage error -- an unrecognised flag, an unreadable ini -- dies
        # before the report plugin writes anything. This is the exact shape
        # that read as "caught" in one of the three broken runners.
        return NodeResult("missing", detail="pytest wrote no JUnit report")
    root = ET.parse(report).getroot()
    cases = [case for case in root.iter("testcase") if _node_id(case) == nodeid]
    if len(cases) != 1:
        return NodeResult(
            "missing",
            detail=(
                f"the report holds {len(cases)} records matching {nodeid}; "
                "one and only one is a usable verdict"
            ),
        )
    case = cases[0]
    failure = case.find("failure")
    if failure is not None:
        # `message` is the observed failing value; `text` is the longrepr,
        # which echoes the test's own source. Only the former is evidence
        # about behaviour. See the module docstring, oracle 4.
        return NodeResult(
            "failed",
            message=failure.get("message", ""),
            detail=(failure.text or "").strip(),
        )
    error = case.find("error")
    if error is not None:
        # Setup, teardown, or collection blew up, so the assertion under test
        # never ran. That is not a tripwire firing.
        return NodeResult(
            "errored",
            message=error.get("message", ""),
            detail=(error.text or "").strip(),
        )
    if case.find("skipped") is not None:
        return NodeResult("missing", detail="the test was skipped, so it judged nothing")
    return NodeResult("passed")


def _write_atomic(path: Path, payload: bytes) -> None:
    """Replace a file's bytes without ever leaving it half-written.

    A plain `write_bytes` interrupted by Ctrl-C, a kill, or a disk error leaves
    the source truncated, which is worse than leaving it mutated: the mutation
    is one known edit, and a truncation is not. `os.replace` is atomic on NTFS
    and POSIX alike.

    Bytes rather than text throughout, so a restore on Windows cannot come back
    as a line-ending diff.
    """

    handle, staging = tempfile.mkstemp(dir=str(path.parent), prefix=STAGING_PREFIX)
    try:
        with os.fdopen(handle, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        # os.replace carries the staging file's mode onto the destination, and
        # mkstemp creates at 0600. Without this a restore would silently narrow
        # the source file's permissions on POSIX -- git tracks only the
        # executable bit, so nothing would report it.
        shutil.copymode(path, staging)
        os.replace(staging, path)
    except BaseException:
        Path(staging).unlink(missing_ok=True)
        raise


def undiscriminating_expect(expect: str) -> str | None:
    """Why this `expect` could not tell one failure from another, or None.

    `probe` already refused an empty `expect`, because `"" in message` is
    always true. `"AssertionError:" in message` is always true for the
    identical structural reason, and it is far likelier to be written: the
    message every Python assertion produces starts with it, and `--emit-expect`
    prints that prefix. Measured on this file's own canaries -- with
    `expect="AssertionError:"` both of the two that carry the most weight go
    CAUGHT on the wrong branch and the whole of oracle 4 evaporates, with no
    code edited anywhere. The guard that existed was the right guard stopping
    one step too early.

    The rule: strip a leading `SomeError: ` and any trailing colon, and what
    remains must not be a single bare word. A class name is a fact about
    Python; the observed failing value is a fact about the behaviour.

    This does reject a legitimate one-word pin such as `halted`. That is
    deliberate -- a single word rarely distinguishes two failures of the same
    test, which is the thing `expect` exists to do -- and the remedy is to pin
    more of the line, which `--emit-expect` prints.
    """

    if not expect:
        return "the entry pins no failure message, so nothing could discriminate"
    body = expect.split(": ", 1)[1] if ": " in expect else expect
    body = body.strip().rstrip(":").strip()
    if not body:
        return (
            f"{expect!r} is an exception class and nothing else, so it matches "
            "every failure of this test rather than the one the entry names"
        )
    if _BARE_WORD.match(body):
        return (
            f"{expect!r} reduces to the bare word {body!r}, which does not "
            "distinguish this failure from another failure of the same test"
        )
    return None


class RestoreFailed(RuntimeError):
    """The working tree may still hold a mutation. Nothing else may run."""


def probe(
    path: Path,
    old: str,
    new: str,
    nodeid: str,
    expect: str,
    *,
    importable: tuple[str, Path] | None,
    cwd: Path,
) -> Verdict:
    """Apply one mutation, judge the named test, and put the file back.

    The single verdict path in this file. The table and the self-check in
    `tests/test_mutations.py` are its only two callers, on purpose: a
    self-check that exercised a different code path would validate something
    other than the thing that runs, which is the defect class this whole file
    is about.

    `importable` is `(dotted_name, sys_path_entry)`, or None to skip oracle 1
    for a target that is not importable Python.
    """

    if old == new:
        return Verdict(STALE, "the entry's old and new text are identical")
    undiscriminating = undiscriminating_expect(expect)
    if undiscriminating is not None:
        return Verdict(STALE, undiscriminating)

    original = path.read_bytes()
    text = original.decode("utf-8")
    occurrences = text.count(old)
    if occurrences == 0:
        return Verdict(STALE, f"anchor not found in {path.name}; the entry is out of date")
    if occurrences > 1:
        # Which site was mutated decides which behaviour was deleted. If that
        # is unknown, so is the meaning of any verdict -- so this is never a
        # green, it is an entry that must be made specific.
        return Verdict(
            AMBIGUOUS,
            f"anchor appears {occurrences} times in {path.name}; it no longer names one site",
        )

    clean = _run_node(nodeid, cwd)
    if clean.outcome == "missing":
        return Verdict(NO_SUCH_TEST, clean.detail or f"pytest could not run {nodeid}")
    if clean.outcome != "passed":
        # Grading a mutation against an already-red test says nothing. This is
        # oracle 5, and no argument to `probe` can turn it off -- a per-entry
        # knob for this is one a caller would reach for on the run where it
        # matters. (`--skip-self-check` in `main` is a different thing: it
        # skips a duplicate run of the self-check, not any oracle.)
        return Verdict(
            BASELINE_RED,
            f"{nodeid} does not pass on the clean tree: {clean.message or clean.outcome}",
        )

    mutated = text.replace(old, new)
    if mutated == text or new not in mutated:
        return Verdict(STALE, "the replacement did not change the file")

    try:
        _write_atomic(path, mutated.encode("utf-8"))
        if importable is not None:
            module, path_entry = importable
            broken = _import_check(module, path_entry, cwd)
            if broken is not None:
                return Verdict(BROKEN, broken)
        result = _run_node(nodeid, cwd)
    finally:
        _restore(path, original)

    if result.outcome == "missing":
        return Verdict(NO_SUCH_TEST, result.detail or f"pytest could not run {nodeid}")
    if result.outcome == "errored":
        return Verdict(
            ERRORED,
            f"{nodeid} errored rather than failed, so its assertion never ran: {result.message}",
        )
    if result.outcome == "passed":
        return Verdict(
            SURVIVED,
            f"{nodeid} passed with the behaviour deleted; the tripwire no longer catches it",
        )
    if expect not in result.message:
        # The test went red, but not for the reason the entry claims. Reporting
        # that as CAUGHT would credit this entry with a coverage it does not
        # have -- "this test is red" standing in for "this behaviour is caught
        # by this assertion".
        return Verdict(
            WRONG_REASON,
            f"{nodeid} failed without {expect!r} in its failure message: {result.message}",
        )
    return Verdict(CAUGHT)


def _import_check(module: str, path_entry: Path, cwd: Path) -> str | None:
    """Oracle 1: refuse to grade a mutation that only broke the parser.

    `PYTHONPATH` is set explicitly rather than inherited. Without it this
    subprocess resolves the module through whatever the venv installed, which
    is not the rule pytest uses -- `pytest.ini` sets `pythonpath = src`. Today
    both land on the same file because the install is editable. Under a
    non-editable install they would diverge, this check would import an
    unmutated copy, always succeed, and BROKEN would never fire again.
    """

    env = dict(os.environ)
    env["PYTHONPATH"] = str(path_entry)
    completed = subprocess.run(
        [PYTHON, "-c", f"import {module}"],
        cwd=str(cwd),
        env=env,
        capture_output=True,
        text=True,
    )
    if completed.returncode == 0:
        return None
    last = (completed.stderr or "").strip().splitlines()
    return f"the mutated {module} does not import: {last[-1] if last else 'no output'}"


def _restore(path: Path, original: bytes) -> None:
    """Put the file back and prove it, byte for byte."""

    _write_atomic(path, original)
    if path.read_bytes() != original:
        # `relative_to` raises for a path outside the repo, which is the case
        # in the self-check's temp dirs -- and a ValueError raised while
        # building this message would mask the failure it is reporting.
        try:
            recover = path.resolve().relative_to(ROOT).as_posix()
        except ValueError:
            recover = str(path)
        raise RestoreFailed(
            f"{path} was not restored. The working tree still holds a mutation. "
            f"Recover with: git checkout -- {recover}"
        )


# --------------------------------------------------------------------------
# The table.
#
# Every entry's `expect` was captured from an observed failure via
# --emit-expect, never written from belief about what the failure would say.
# --------------------------------------------------------------------------

CLI = "src/agent_workflows_harness/cli.py"
CLI_MODULE = "agent_workflows_harness.cli"

ENTRIES: list[Entry] = []


def entry(**kwargs: object) -> Entry:
    item = Entry(**kwargs)  # type: ignore[arg-type]
    ENTRIES.append(item)
    return item


entry(
    name="bare-path-space",
    target=CLI,
    module=CLI_MODULE,
    old='"ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789@+=:,./-_"',
    new='"ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789@+=:,./-_ "',
    test=(
        "tests/test_ontology.py::"
        "test_a_quoted_path_survives_every_shell_the_hint_may_be_pasted_into"
    ),
    # Names the fixture whose behaviour broke, so this entry cannot be
    # satisfied by the sibling entry below failing on a different fixture --
    # which is exactly what happened while the match was against the failure
    # *text*, since both literals live in one tuple above every assertion.
    expect="AssertionError: /home/me/my tbox/t.json",
    note=(
        "A space in the bare-safe set means a path with a space is emitted "
        "unquoted, and the hint breaks in every shell. This is the issue's own "
        "strongest instance: the assertion was there, but every spaced fixture "
        "also carried a backslash, so the space rule was forced by the "
        "backslash and would have gone unpinned on a platform without one."
    ),
)

entry(
    name="quote-escaping",
    target=CLI,
    module=CLI_MODULE,
    old=r"""path.replace('"', '\\"')""",
    new="path",
    test=(
        "tests/test_ontology.py::"
        "test_a_quoted_path_survives_every_shell_the_hint_may_be_pasted_into"
    ),
    expect='AssertionError: /home/me/od"d/t.json',
    note=(
        "Without the escape, a path carrying a double quote closes the quoted "
        "string early and the rest of the hint becomes argv. The only fixture "
        "reaching this branch is the POSIX one, since the character is illegal "
        "in a Windows filename."
    ),
)


def load_table() -> list[Entry]:
    """The table, as data. Imported by the self-check for its lint."""

    return list(ENTRIES)


def find_entry(name: str, entries: list[Entry] | None = None) -> Entry:
    for item in entries if entries is not None else ENTRIES:
        if item.name == name:
            return item
    raise KeyError(name)


def _importable_for(item: Entry, root: Path = ROOT) -> tuple[str, Path] | None:
    """The wire from a table entry to oracle 1.

    Oracle 1 itself is pinned five ways, but this is what hands it its
    argument, and it was unpinned: returning None here silently disables the
    import check for *every real entry* while every oracle-1 canary stays
    green, because those pass `importable` explicitly. A syntax-error mutation
    would then be graded instead of reported BROKEN. The oracle was tested and
    the wire to it was not.
    """

    if item.module is None:
        return None
    return (item.module, root / item.path_entry)


def verify_import_rule(
    entries: list[Entry] | None = None, root: Path | None = None
) -> str | None:
    """Assert an entry's `module` and `target` name the same file.

    Both sides are derived from the entry's own fields -- `target` directly,
    and `module` resolved under `path_entry` by pytest's rule -- so this is an
    entry-consistency check, not an environmental one. It catches an entry
    whose three fields disagree, which would otherwise mutate one file and
    import-check another.

    Say that precisely, because an earlier version resolved through
    `importlib.util.find_spec` and could therefore also see a non-editable
    install shadowing `src/`. That was strictly more, and the summary line kept
    promising it after the body stopped delivering it. Twice, in fact: this
    docstring described `find_spec` for a while after the rewrite, and then
    still claimed to "assert the runner mutates the file the suite imports"
    after that was corrected. Third and fourth occurrences in this file of
    prose asserting a control that had moved.

    The environmental half is not lost -- it lives in
    `test_the_suite_mutates_the_source_tree_it_imports`, which pins
    `pythonpath = src` in pytest.ini and resolves the package for real -- and
    it is not here.
    """

    root = root if root is not None else ROOT
    for item in entries if entries is not None else ENTRIES:
        if item.module is None:
            continue
        # Resolved by pytest's rule -- `path_entry` on sys.path, dotted name
        # under it -- rather than through the runner's own interpreter. Two
        # reasons. `find_spec` follows whatever the venv installed, which is
        # not what `pythonpath = src` in pytest.ini does, so under a
        # non-editable install the two would diverge and this check would bless
        # a file the suite never runs. And it made the runner refuse to work in
        # a copy of the repo, which is exactly where a reviewer measures.
        landing = root / item.path_entry / Path(*item.module.split(".")).with_suffix(".py")
        target = root / item.target
        if not landing.exists():
            return (
                f"{item.module} does not resolve to a file under "
                f"{item.path_entry}/; the entry names a module that is not there"
            )
        if landing.resolve() != target.resolve():
            return (
                f"the runner would mutate {target}, but {item.module} resolves "
                f"to {landing}; the table would grade a file the suite does not import"
            )
    return None


# --------------------------------------------------------------------------
# The driver.
# --------------------------------------------------------------------------


class LockHeld(RuntimeError):
    """Another run holds the lock. Distinct from every verdict."""


class _Lock:
    """Refuse to run two mutation runs against one working tree.

    Two runners interleaving mutations restore each other's originals, and the
    tree can end up holding an edit neither of them made. `O_EXCL` is the whole
    mechanism; the file is removed on the way out.
    """

    def __init__(self, path: Path) -> None:
        self.path = path
        self._handle: int | None = None

    def __enter__(self) -> "_Lock":
        try:
            self._handle = os.open(str(self.path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError:
            raise LockHeld(
                f"another mutation run holds {self.path}. Runs mutate a shared "
                "working tree and must not overlap. If no run is active, remove it."
            ) from None
        os.write(self._handle, str(os.getpid()).encode("ascii"))
        return self

    def __exit__(self, *exc: object) -> None:
        if self._handle is not None:
            os.close(self._handle)
        self.path.unlink(missing_ok=True)


def _full_suite_is_green(cwd: Path) -> str | None:
    """Oracle 5, the outer half. A red tree grades nothing."""

    completed = subprocess.run(
        [PYTHON, "-m", "pytest", "-q", "-p", "no:cacheprovider"],
        cwd=str(cwd),
        capture_output=True,
        text=True,
    )
    if completed.returncode == 0:
        return None
    tail = (completed.stdout or "").strip().splitlines()[-5:]
    return "the suite is not green before any mutation:\n  " + "\n  ".join(tail)


def _collected_node_ids(cwd: Path) -> set[str]:
    """Every nodeid pytest can address, for the preflight in `run_table`."""

    completed = subprocess.run(
        [PYTHON, "-m", "pytest", "-q", "-p", "no:cacheprovider", "--collect-only"],
        cwd=str(cwd),
        capture_output=True,
        text=True,
    )
    return {
        line.strip()
        for line in (completed.stdout or "").splitlines()
        if "::" in line and not line.startswith(" ")
    }


def run_table(
    entries: list[Entry], collected: set[str], cwd: Path = ROOT, root: Path | None = None
) -> list[tuple[Entry, Verdict]]:
    """Grade every entry, reporting a stale one as stale and never as green.

    `collected` is passed in rather than derived here, and the caller refuses
    to run on an empty one. Deriving it inside meant guarding with
    `if collected and ...`, which turns a parse that stopped yielding node ids
    into a silently skipped preflight -- a derived haystack with a vacuity
    guard instead of a non-empty guard, which is the house rule's own example.
    """

    root = root if root is not None else ROOT
    results: list[tuple[Entry, Verdict]] = []
    for item in entries:
        # Preflight, before anything is written: a nodeid that no longer exists
        # is a table defect, and finding that out without touching the tree is
        # strictly better than finding it out with a mutation in place.
        if item.test not in collected:
            results.append(
                (item, Verdict(NO_SUCH_TEST, f"{item.test} is not collected by this suite"))
            )
            continue
        verdict = probe(
            root / item.target,
            item.old,
            item.new,
            item.test,
            item.expect,
            importable=_importable_for(item, root),
            cwd=cwd,
        )
        results.append((item, verdict))
        print(f"  {verdict.name:<13} {item.name:<22} {item.test}")
    return results


def recommended_pin(message: str) -> str:
    """The line `--emit-expect` tells an author to paste.

    The first line of the failure message, prefix included. Named and pinned
    because this is the authoring path: a degraded version hands the author a
    bad `expect`, the author pastes it in good faith, and every one of the six
    oracles then agrees with it perfectly. That is this issue's defect class
    upstream of every oracle rather than inside one, and it is the only layer
    where being wrong is self-sealing.

    Line 2 is `assert (False)` and the like -- satisfiable by an enormous class
    of unrelated failures, and stripped of the `AssertionError: ` prefix that
    the module docstring names as one of two independent guards.
    """

    return message.splitlines()[0] if message else ""


def emit_expect(item: Entry, cwd: Path = ROOT, root: Path | None = None) -> int:
    """Print the failure message an entry's mutation actually produces.

    The authoring rule this supports is the point: `expect` is copied from an
    observed failure, never written from belief about what the failure says. A
    guessed `expect` is one more assertion nobody watched fail.
    """

    target = (root if root is not None else ROOT) / item.target
    original = target.read_bytes()
    text = original.decode("utf-8")
    if text.count(item.old) != 1:
        print(f"anchor appears {text.count(item.old)} times; it must appear exactly once")
        return EXIT_UNEVALUABLE
    # The named test must pass before the mutation, or the message printed
    # below describes a failure that was already there and the author pins a
    # string with nothing to do with their entry.
    clean = _run_node(item.test, cwd)
    if clean.outcome != "passed":
        print(f"{item.test} does not pass on the clean tree; there is nothing to pin yet")
        return EXIT_UNEVALUABLE
    try:
        _write_atomic(target, text.replace(item.old, item.new).encode("utf-8"))
        result = _run_node(item.test, cwd)
    finally:
        _restore(target, original)
    # Name the entry. Without it, a `find_entry` that returned the wrong one
    # would print another entry's pin with nothing in the output saying so, and
    # the author would paste it in good faith.
    print(f"entry: {item.name} -> {item.test}")
    print(f"outcome: {result.outcome}")
    if result.outcome != "failed":
        print("the mutation did not make the named test fail, so there is nothing to pin")
        return EXIT_UNEVALUABLE
    # Paste the FIRST line, prefix included. "Find a distinctive line" would
    # invite dropping the `AssertionError: ` prefix, and that prefix is one of
    # the two independent guards described in the module docstring -- a source
    # echo never carries it.
    print("--- paste this first line into expect, prefix AND the value after it ---")
    print(recommended_pin(result.message))
    print("--- full failure message, for choosing a longer pin if you need one ---")
    print(result.message)
    # The failing location is the one fact that lets an author notice their
    # mutation breaks the named test at an assertion that has nothing to do
    # with the behaviour they are claiming. Without it this path is
    # self-sealing: a wrong pin is handed to the author, and every check
    # downstream then agrees with the wrong pin.
    located = [line for line in result.detail.splitlines() if ": " in line and ".py:" in line]
    if located:
        print("--- it failed here; check this is the assertion your entry claims ---")
        print(located[-1].strip())
    if ADDRESS_PATTERN.search(result.message):
        print("--- note: this message carries a memory address; do not pin that part ---")
    return EXIT_OK


def first_failing_precondition(
    checks: list[tuple[int, Callable[[], str | None]]],
) -> tuple[int | None, str]:
    """Run the preconditions in order and stop at the first failure.

    The order is the policy, not an implementation detail: an untrusted oracle
    must produce no verdicts at all, so the self-check has to abort the run
    before the table is graded rather than alongside it. Extracted from `main`
    so that ordering can be pinned by a canary that asserts the later checks
    were never called -- inside `main` it was unfalsifiable, and a run whose
    self-check failed could still have graded the table with nothing noticing.

    Each check returns a failure message, or None when it passes.
    """

    for code, check in checks:
        failure = check()
        if failure is not None:
            return code, failure
    return None, ""


def report_results(
    results: list[tuple[Entry, Verdict]],
    *,
    suite_size: int | None = None,
    self_check_skipped: bool = False,
) -> int:
    """Turn verdicts into the summary and the exit code a human acts on.

    Separated and pinned by canaries because this is where a correct verdict
    can still be thrown away. Measured on an earlier revision: dropping
    `WRONG_REASON` from `UNEVALUABLE` made a failed entry vanish from the
    summary and the run exit 0, while every canary stayed green -- the
    computation was right and the channel carrying it to a human was not. The
    oracles all judge a mutation; none of them judged this.
    """

    caught = [(i, v) for i, v in results if v.ok]
    survived = [(i, v) for i, v in results if v.name == SURVIVED]
    unevaluable = [(i, v) for i, v in results if v.name in UNEVALUABLE]

    # The three buckets must partition the results. A verdict that lands in
    # none of them would disappear from both the summary and the exit code,
    # which is how the degradation above stayed invisible. A verdict this
    # function cannot place is a runner bug, and a runner bug is never a green.
    unplaced = [
        (item, verdict)
        for item, verdict in results
        if not verdict.ok and verdict.name != SURVIVED and verdict.name not in UNEVALUABLE
    ]
    if unplaced:
        print(f"\nrunner bug: {len(unplaced)} verdicts fit no bucket and would be discarded")
        for item, verdict in unplaced:
            print(f"  {item.name} [{verdict.name}]")
        return EXIT_SELF_CHECK

    # The summary names its own narrowness. A table covering one test out of a
    # hundred still prints a green, and a reader who takes that for a
    # suite-wide result has been misled by the shape of the line rather than by
    # anything false in it.
    covered = len({item.test for item, _ in results})
    scope = f"{len(results)} entries covering {covered} test" + ("s" if covered != 1 else "")
    if suite_size:
        scope += f" of {suite_size}"
    print(
        f"\n{scope}: {len(caught)} caught, "
        f"{len(survived)} survived, {len(unevaluable)} unevaluable"
    )
    if self_check_skipped:
        # Otherwise the only evidence is one missing line at the top of a run
        # nobody kept, and the docstring's claim that the oracle is validated
        # rather than asserted was conditional on a flag that left no trace.
        print("WARNING: --skip-self-check was used; the runner's own oracle was not validated")
    # Two footers, not one. A survivor is a finding about a test; an
    # unevaluable entry is a finding about the table. Printing them together
    # makes the reader work out which they are looking at.
    for label, group in (("SURVIVED", survived), ("UNEVALUABLE", unevaluable)):
        if not group:
            continue
        print(f"\n{label}")
        for item, verdict in group:
            print(f"  {item.name} [{verdict.name}]")
            print(f"    test:  {item.test}")
            print(f"    anchor: {item.old.strip()[:100]}")
            print(f"    {verdict.detail}")
            print(f"    why it matters: {item.note}")
    if survived:
        return EXIT_SURVIVED
    if unevaluable:
        return EXIT_UNEVALUABLE
    return EXIT_OK


def main(
    argv: list[str] | None = None,
    root: Path | None = None,
    entries: list[Entry] | None = None,
) -> int:
    """Wire the pieces together and return the exit code a human acts on.

    `root` and `entries` are parameters so this can be driven against a
    fixture. Everything it wires was unfalsifiable while they were globals:
    six separate degradations of this function left all 60 canaries green,
    including re-losing the import check on the authoring path -- the same
    control, for the third time, held in place by nothing but a comment
    narrating the previous two losses.
    """

    root = root if root is not None else ROOT
    entries = entries if entries is not None else ENTRIES
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--emit-expect",
        metavar="NAME",
        help="Apply one entry's mutation and print the failure message to pin.",
    )
    parser.add_argument(
        "--skip-self-check",
        action="store_true",
        help=(
            "Skip the dedicated self-check run. For iterating on an entry only. "
            "This does not fully disable validation -- the full-suite check "
            "below collects tests/test_mutations.py anyway -- it skips a "
            "duplicate run of it, and the summary says so when it is used."
        ),
    )
    args = parser.parse_args(argv)

    try:
        with _Lock(root / LOCK_NAME):
            # Above the --emit-expect branch, not below it. This check was
            # main's first statement, the lock refactor moved it under the
            # early return, and restoring it left it with no falsifier -- so
            # putting it back below is invisible. The same control lost three
            # times, twice on the authoring path, held in place by a comment
            # both times. `test_the_authoring_path_still_verifies_the_import_rule`
            # is what holds it now; this comment is only the history.
            drift = verify_import_rule(entries, root)
            if drift is not None:
                print(drift)
                return EXIT_SELF_CHECK

            if args.emit_expect:
                try:
                    item = find_entry(args.emit_expect, entries)
                except KeyError:
                    print(f"no entry named {args.emit_expect!r}")
                    return EXIT_UNEVALUABLE
                return emit_expect(item, cwd=root, root=root)

            code, message = first_failing_precondition(
                [
                    (EXIT_SELF_CHECK, lambda: _self_check(args.skip_self_check, cwd=root)),
                    (EXIT_UNEVALUABLE, lambda: _full_suite_is_green(root)),
                ]
            )
            if code is not None:
                print(message)
                return code

            collected = _collected_node_ids(root)
            if not collected:
                # The preflight's haystack. Empty means the collection parse
                # yielded nothing, not that the suite has no tests, so grading
                # would proceed with the preflight silently doing nothing.
                print("could not enumerate the suite's node ids; refusing to grade blind")
                return EXIT_UNEVALUABLE

            print(f"grading {len(entries)} entries")
            try:
                results = run_table(entries, collected, cwd=root, root=root)
            except (RestoreFailed, OSError) as exc:
                # RestoreFailed means the tree is verified wrong. An OSError may
                # come from anywhere in probe -- a temp dir, a subprocess, the
                # read -- but it can also come from the restore write, and the
                # two are not distinguishable here. Reported as the worse case
                # rather than escaping as an unhandled exception, whose exit
                # would otherwise have collided with a survivor's.
                print(str(exc))
                return EXIT_RESTORE_FAILED

            # Inside the try, not after it. The crash guard below exists so an
            # exception cannot exit 1 and impersonate a lost tripwire, and the
            # reporting layer was the one layer sitting outside it -- the
            # newest layer, added because it had been found unvalidated.
            return report_results(
                results, suite_size=len(collected), self_check_skipped=args.skip_self_check
            )
    except RestoreFailed as exc:
        # From emit_expect's restore. Without this it fell to the crash handler
        # and a verified-dirty tree was reported as an unexplained failure.
        print(str(exc))
        return EXIT_RESTORE_FAILED
    except LockHeld as exc:
        print(str(exc))
        return EXIT_LOCKED
    except Exception as exc:  # noqa: BLE001 - the alternative is exit 1, see below
        # An unexpected crash used to escape as exit 1, which is the code for a
        # lost tripwire. Any exit this runner emits is read as a claim about
        # the tests, so a crash must not be able to impersonate one.
        print(f"the runner failed unexpectedly: {type(exc).__name__}: {exc}")
        return EXIT_UNEXPECTED


def _self_check(
    skipped: bool, cwd: Path = ROOT, target: str = "tests/test_mutations.py"
) -> str | None:
    """Validate the runner's own oracle before it produces any verdict.

    `cwd` and `target` are parameters so the red path can be driven against a
    fixture. Extracting the gate *ordering* into `first_failing_precondition`
    made the ordering falsifiable and left this unfalsifiable: making the body
    `return None` unconditionally left the whole self-check green, so a red
    oracle would have aborted nothing.
    """

    if skipped:
        return None
    print("validating the runner's own oracle")
    completed = subprocess.run(
        [PYTHON, "-m", "pytest", "-q", "-p", "no:cacheprovider", target],
        cwd=str(cwd),
        capture_output=True,
        text=True,
    )
    if completed.returncode == 0:
        return None
    return f"{completed.stdout}\nthe runner's oracle is not trustworthy; no verdicts were produced"


if __name__ == "__main__":
    raise SystemExit(main())
