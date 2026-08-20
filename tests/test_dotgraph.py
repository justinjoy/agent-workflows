from __future__ import annotations

import dataclasses
import os
import re
import subprocess
import sys
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path

import pytest

from agent_workflows_harness.dotgraph import (
    GRAPH_FILENAME_FORMAT,
    build_dot,
    graph_filename,
    write_graph,
)
from agent_workflows_harness.models import (
    BlockedSkill,
    RequestFacts,
    SelectedSkill,
    SkillPlan,
)
from agent_workflows_harness.ontology import (
    DEFAULT_ONTOLOGY,
    Derivation,
    Ontology,
    derive,
)


MOMENT = datetime(2026, 8, 18, 11, 19, 7, 250000, tzinfo=UTC)
# Every character Windows forbids in a filename, plus the POSIX separator.
ILLEGAL_IN_A_FILENAME = set('<>:"/\\|?*')

_DECLARATION = re.compile(r'^\s*("(?:[^"\\]|\\.)*")\s*\[')
_QUOTED = re.compile(r'"(?:[^"\\]|\\.)*"')


def _plan(*, selected=(("10", "inspect-repository", "code_change_requires_repository_context"),),
          blocked=(), properties=("non_trivial",)) -> SkillPlan:
    return SkillPlan(
        request=RequestFacts.from_properties(set(properties)),
        selected=tuple(
            SelectedSkill(order=int(order), skill_id=skill_id, reason=reason)
            for order, skill_id, reason in selected
        ),
        blocked=tuple(
            BlockedSkill(skill_id=skill_id, reason=reason) for skill_id, reason in blocked
        ),
    )


def _unescape(text: str) -> str:
    """Undo DOT's string escaping.

    A generic inverse over `\\(.)` rather than a copy of _escape's ordered
    replaces: restating those would make an assertion agree with the
    implementation by construction. The table holds only the escapes that are
    not self-inverse, so it grows when the escaped set does; the generic
    fallback covers the rest.
    """

    return re.sub(
        r"\\(.)", lambda match: {"n": "\n", "r": "\r"}.get(match.group(1), match.group(1)), text
    )


def _declared_nodes(dot: str) -> set[str]:
    return {
        match.group(1)
        for line in dot.splitlines()
        if (match := _DECLARATION.match(line))
    }


def _edges(dot: str) -> list[tuple[str, str]]:
    """Every edge, including the chained ones an invisible ordering edge uses."""

    found: list[tuple[str, str]] = []
    for line in dot.splitlines():
        if "->" not in line:
            continue
        ids = _QUOTED.findall(line.split("[", 1)[0])
        found.extend(zip(ids, ids[1:]))
    return found


def test_the_graph_filename_is_sortable_and_legal_on_every_platform():
    # Hardcoded, not rebuilt from GRAPH_FILENAME_FORMAT: formatting the
    # constant with the same datetime restates the implementation and passes
    # under any change to it, including one that reintroduces a colon.
    assert graph_filename(MOMENT) == "agent-workflows-20260818T111907250000Z.dot"

    assert not ILLEGAL_IN_A_FILENAME & set(graph_filename(MOMENT))
    assert graph_filename(MOMENT).startswith("agent-workflows-")
    assert graph_filename(MOMENT).endswith(".dot")

    later = MOMENT.replace(microsecond=250001)
    assert graph_filename(MOMENT) < graph_filename(later), "sorts chronologically"
    assert "%" not in GRAPH_FILENAME_FORMAT.replace("%Y", "").replace("%m", "").replace(
        "%d", ""
    ).replace("%H", "").replace("%M", "").replace("%S", "").replace("%f", ""), (
        "every directive is fixed width, or lexicographic order is not chronological"
    )


def test_a_moment_in_another_zone_is_named_in_the_utc_the_suffix_claims():
    # The name ends in Z, so an offset datetime must be converted rather than
    # formatted where it stands -- otherwise the file claims a UTC instant it
    # does not hold, and two runs an hour apart can sort backwards.
    elsewhere = MOMENT.astimezone(timezone(timedelta(hours=9)))

    assert graph_filename(elsewhere) == graph_filename(MOMENT)
    assert graph_filename(elsewhere) == "agent-workflows-20260818T111907250000Z.dot"
    # No assertion here for the naive case the docstring describes: it is read
    # as local time, so any check of it passes for free wherever local time is
    # UTC -- which is every CI runner. An assertion that cannot fail where it
    # runs is the shape this repo's mutation table exists to reject.


def test_the_graph_content_is_deterministic_for_one_moment():
    # Against a row-permuted TBox, not the same object twice. Two builds from
    # one Ontology iterate the identical tuples in the identical order, so they
    # agree whether or not anything is sorted -- the assertion would be
    # satisfied by per-process iteration order and every sorted() in the module
    # could be deleted with this test still green.
    permuted = dataclasses.replace(
        DEFAULT_ONTOLOGY,
        sub_class_of=tuple(reversed(DEFAULT_ONTOLOGY.sub_class_of)),
        surface_class=tuple(reversed(DEFAULT_ONTOLOGY.surface_class)),
        skill_class=tuple(reversed(DEFAULT_ONTOLOGY.skill_class)),
        property_of_class=tuple(reversed(DEFAULT_ONTOLOGY.property_of_class)),
        scope_property=tuple(reversed(DEFAULT_ONTOLOGY.scope_property)),
    )
    plan = _plan()

    first = build_dot(DEFAULT_ONTOLOGY, plan, moment=MOMENT)
    second = build_dot(permuted, plan, moment=MOMENT)

    assert first == second, "row order in the TBox reached the output"
    assert len(_edges(first)) > 40, "the bundled TBox has more rows than this"


_CROSS_PROCESS_BUILD = """
import sys
from datetime import UTC, datetime
sys.path.insert(0, {src!r})
from agent_workflows_harness.dotgraph import build_dot
from agent_workflows_harness.models import BlockedSkill, RequestFacts, SelectedSkill, SkillPlan
from agent_workflows_harness.ontology import DEFAULT_ONTOLOGY, Derivation, derive

plan = SkillPlan(
    # Several held properties, several orphan derivations: a set of one is
    # sorted by accident, so a one-property request cannot reach sorted(held).
    request=RequestFacts.from_properties({{"docs_only", "multi_file", "needs_tests"}}),
    selected=(SelectedSkill(order=10, skill_id="inspect-repository", reason="a"),),
    blocked=(BlockedSkill(skill_id="run-broad-tests", reason="b"),),
)
# Two orphan derivations and several held properties: the sorts over sets are
# unreachable with one of each.
derivations = derive(("readme", "changelog"), ("one_line",)) + (
    Derivation(request_property="needs_tests", source="touches(req, readme)",
               path=("DocSurface", "needs_tests")),
    # A third orphan: with two, whether de-sorting them changes the bytes is a
    # coin flip per seed, and only one of this test's three seeds caught it.
    Derivation(request_property="needs_review", source="touches(req, changelog)",
               path=("DocSurface", "needs_review")),
)
sys.stdout.buffer.write(build_dot(DEFAULT_ONTOLOGY, plan, derivations,
                                  moment=datetime(2026, 8, 18, 11, 19, 7, 250000, tzinfo=UTC)
                                  ).encode("utf-8"))
"""


def _build_in_subprocess(seed: str) -> str:
    environment = dict(os.environ, PYTHONHASHSEED=seed)
    source = str(Path(__file__).resolve().parents[1] / "src")
    # Bytes on both ends, because naming a codec on the child alone is
    # silently green: the UTF-8 bytes of the graph's own glyphs are every one
    # of them a valid cp1252 character, so a parent decoding with the ambient
    # locale gets mojibake without raising -- the same mojibake for every seed,
    # which is a green comparison over garbage rather than a visible failure.
    # (Naming it on the parent alone is merely loud: the child raises first.)
    #
    # Text mode would also route the graph through the platform's newline
    # translation on the way out and back on the way in. That one is a property
    # of the transport rather than a live tripwire here -- these children all
    # run on one platform, so a CR change would be uniform across seeds and
    # this test could not see it either way.
    finished = subprocess.run(
        [sys.executable, "-c", _CROSS_PROCESS_BUILD.format(src=source)],
        capture_output=True,
        env=environment,
    )
    # Not check=True: it renders the whole script as one escaped argv string
    # and leaves the child's traceback sitting unread in stderr. stderr decodes
    # leniently so a traceback can never hide behind a second decode error;
    # stdout decodes strictly, because malformed UTF-8 out of build_dot is
    # itself the defect this test would be reporting.
    assert finished.returncode == 0, finished.stderr.decode("utf-8", "replace")
    return finished.stdout.decode("utf-8")


def test_the_graph_is_byte_identical_across_processes():
    # Set iteration order is randomized per process, and only per process, so
    # this is the one fixture that reaches every sort in the module -- the
    # property set, the orphan edge set, and the request's own held properties,
    # each of which could be de-sorted with the whole suite green when
    # determinism was checked inside a single interpreter.
    outputs = {_build_in_subprocess(seed) for seed in ("0", "1", "524287")}

    (only,) = outputs
    assert "label=\"derived\"" in only, "the orphan-edge branch must actually run"
    assert len(_edges(only)) > 40
    # Every other assertion here is ASCII-only, so a transport that decoded
    # with the ambient locale would satisfy all of them over mojibake. This
    # glyph makes that visible: a cp1252 decode turns its three UTF-8 bytes
    # into the three characters `âŠ‘`. It is also the only character in the
    # graph with no cp1252 encoding at all, which is why the child crashed
    # outright rather than mangling quietly -- `·` encodes there fine.
    assert "⊑" in only, "the graph came back decoded with the wrong codec"


def test_a_windows_path_in_a_label_survives_as_the_path_it_was():
    # test_a_quote_in_a_label_cannot_break_out_of_the_dot_string already pins
    # that a backslash is escaped, and survives an _escape that escapes it
    # twice over. What nothing else pins is that the escaping is *invertible*:
    # an --ontology path on Windows has to come back out of the label as the
    # path the caller gave. _escape has no platform branch, so a hardcoded
    # native path exercises it from any platform.
    source = r"C:\Users\me\tbox.json"

    dot = build_dot(DEFAULT_ONTOLOGY, _plan(), moment=MOMENT, source=source)
    (label,) = [line for line in dot.splitlines() if "agent-workflows harness run" in line]

    # The round-trip alone: dropping the escape makes the inverse eat `\U`,
    # and over-escaping leaves a doubled backslash behind, so both directions
    # fail here. A "raw path absent from the label" check would add nothing
    # over that, and it is not universally sound either -- where a source's
    # only backslash is a single trailing one, the correctly escaped `C:\\`
    # still contains the raw `C:\`. That case cannot arise from this fixture,
    # so the reason to leave the check out is redundancy, not danger.
    assert f"ontology: {source}" in _unescape(label), "the escaping is not invertible"


def test_the_graph_carries_the_active_tbox_rather_than_the_bundled_default():
    custom = Ontology(
        sub_class_of=(("BillingSurface", "SharedBehavior"), ("SharedBehavior", "Surface")),
        surface_class=(("billing_ledger", "BillingSurface"),),
        skill_class=(),
        property_of_class=(("SharedBehavior", "touches_shared_behavior"),),
        scope_property=(),
    )

    dot = build_dot(custom, _plan(), moment=MOMENT, source="/tmp/custom.json")

    assert '"ind:billing_ledger"' in _declared_nodes(dot)
    assert '"ind:session_module"' not in _declared_nodes(dot), "the default leaked in"
    assert "/tmp/custom.json" in dot, "the label names which TBox this was"


def test_the_graph_highlights_this_runs_selection_and_not_only_the_tbox():
    # Differential: both graphs draw the same TBox, so anything they disagree
    # about is the run layer. The non-empty assertion is the load-bearing one
    # -- a renderer that omits the run layer entirely makes the symmetric
    # difference empty, and "differs only in the run layer" true by vacuity.
    reviewed = _plan(selected=(("80", "review-diff", "every_code_change_requires_review"),))
    broad = _plan(
        selected=(("70", "run-broad-tests", "shared_or_cross_module_behavior_changed"),),
        blocked=(("create-implementation-plan", "risk_facts_do_not_require_explicit_plan"),),
    )

    difference = set(build_dot(DEFAULT_ONTOLOGY, reviewed, moment=MOMENT).splitlines()) ^ set(
        build_dot(DEFAULT_ONTOLOGY, broad, moment=MOMENT).splitlines()
    )

    # Joined rather than asserted with any(): a generator renders as its own
    # repr in the failure, which names neither the reason that went missing nor
    # the run it belonged to.
    rendered = "\n".join(sorted(difference))

    assert difference, "the two runs render identically; the selection is not in the graph"
    assert "every_code_change_requires_review" in rendered
    assert "shared_or_cross_module_behavior_changed" in rendered
    assert (
        "risk_facts_do_not_require_explicit_plan" in rendered
    ), "a blocked skill's reason is part of what the run decided"


def test_a_derivation_is_drawn_as_a_path_through_the_tbox():
    derivation = Derivation(
        request_property="touches_shared_behavior",
        source="touches(req, session_module)",
        path=("session_module", "AuthSurface", "SharedBehavior"),
    )

    plain = build_dot(DEFAULT_ONTOLOGY, _plan(), moment=MOMENT)
    derived = build_dot(DEFAULT_ONTOLOGY, _plan(), (derivation,), moment=MOMENT)

    # The rows exist in both graphs; the derivation restyles the ones this run
    # travelled, so the difference is per-edge and not a second parallel copy.
    assert _edges(plain) == _edges(derived), "a derivation must not add TBox edges"
    travelled = [
        line
        for line in derived.splitlines()
        if "b34700" in line and "->" in line
    ]
    assert len(travelled) == 3, travelled
    assert any('"ind:session_module" -> "cls:AuthSurface"' in line for line in travelled)
    assert any(
        '"cls:SharedBehavior" -> "prop:touches_shared_behavior"' in line
        for line in travelled
    ), "the property_of_class row the path ends on is part of the path"


def test_a_docs_only_derivation_is_drawn_though_no_tbox_row_carries_it():
    # derive() infers docs_only from the absence of a non-doc touch, so unlike
    # every other derivation there is no property_of_class row to restyle.
    derivation = Derivation(
        request_property="docs_only",
        source="touches(req, readme)",
        path=("DocSurface", "docs_only"),
    )

    dot = build_dot(DEFAULT_ONTOLOGY, _plan(properties=("docs_only",)), (derivation,), moment=MOMENT)

    assert any(
        src == '"cls:DocSurface"' and dst == '"prop:docs_only"' for src, dst in _edges(dot)
    )


def test_node_ids_are_namespaced_so_a_surface_and_a_property_cannot_merge():
    # ontology._TERM_PATTERN permits an individual named `trivial`, which is
    # also a request property. Bare ids would collapse them into one node and
    # draw an edge no row asserts.
    custom = Ontology(
        sub_class_of=(("DocSurface", "Surface"),),
        surface_class=(("trivial", "DocSurface"),),
        skill_class=(),
        property_of_class=(),
        scope_property=(("one_line", "trivial"),),
    )

    declared = _declared_nodes(build_dot(custom, _plan(properties=("trivial",)), moment=MOMENT))

    assert '"ind:trivial"' in declared
    assert '"prop:trivial"' in declared


def test_a_class_named_after_a_property_does_not_misdirect_a_derived_path():
    # ontology._TERM_PATTERN permits a class named `trivial`, which is also a
    # request property, and --ontology makes it reachable input. Resolving the
    # last path element by name equality drew a derived edge from the
    # individual straight to the property -- an edge no TBox row asserts --
    # and left the two rows the run really travelled unhighlighted.
    custom = Ontology(
        sub_class_of=(("trivial", "Surface"),),
        surface_class=(("widget", "trivial"),),
        skill_class=(),
        property_of_class=(("trivial", "trivial"),),
        scope_property=(),
    )
    derivation = Derivation(
        request_property="trivial",
        source="touches(req, widget)",
        path=("widget", "trivial"),
    )

    dot = build_dot(custom, _plan(properties=("trivial",)), (derivation,), moment=MOMENT)
    travelled = {
        (line.split(" -> ")[0].strip(), line.split(" -> ")[1].split(" [")[0].strip())
        for line in dot.splitlines()
        if "b34700" in line and " -> " in line
    }

    assert travelled == {
        ('"ind:widget"', '"cls:trivial"'),
        ('"cls:trivial"', '"prop:trivial"'),
    }, travelled
    assert '"ind:widget" -> "prop:trivial"' not in dot, "an edge no row asserts"


def test_an_individual_named_after_the_doc_surface_class_declares_its_endpoints():
    # The one shape _path_nodes cannot tell apart. It may mis-style edges; what
    # it must not do is emit an id nothing declares, which draws a phantom node
    # outside every cluster.
    custom = Ontology(
        sub_class_of=(("DocSurface", "Surface"),),
        surface_class=(("DocSurface", "DocSurface"),),
        skill_class=(),
        property_of_class=(("Surface", "trivial"),),
        scope_property=(),
    )
    derivation = Derivation(
        request_property="docs_only",
        source="touches(req, DocSurface)",
        path=("DocSurface", "docs_only"),
    )

    dot = build_dot(custom, _plan(properties=("docs_only",)), (derivation,), moment=MOMENT)
    undeclared = {node for edge in _edges(dot) for node in edge} - _declared_nodes(dot)

    assert not undeclared, undeclared


def test_an_empty_relation_draws_no_cluster_for_it():
    custom = Ontology(
        sub_class_of=(("DocSurface", "Surface"),),
        surface_class=(("readme", "DocSurface"),),
        skill_class=(),
        property_of_class=(),
        scope_property=(),
    )

    dot = build_dot(custom, _plan(), moment=MOMENT)

    # An empty labelled box asserts a category the TBox does not have.
    assert "cluster_scopes" not in dot
    assert "cluster_individuals" in dot


def test_a_newline_in_a_label_keeps_the_file_line_oriented():
    dot = build_dot(DEFAULT_ONTOLOGY, _plan(), moment=MOMENT, source="/tmp/a\nb.json")

    (label,) = [line for line in dot.splitlines() if "agent-workflows harness run" in line]
    assert "/tmp/a\\nb.json" in label


def test_a_derivation_from_the_real_producer_resolves_to_declared_nodes():
    # Couples this renderer to derive() rather than to a copy of its output.
    # _path_nodes reads the `source` prefix to recognise a scope path, and
    # every other test here hand-builds a Derivation with that prefix written
    # out again -- which duplicates the producer's format instead of depending
    # on it. Rewording ontology.py's prefix would leave those tests green
    # while a real --scope run drew a node nothing declares.
    derivations = derive(("session_module", "readme"), ("one_line",))

    assert {item.request_property for item in derivations} == {
        "touches_shared_behavior",
        "trivial",
    }, derivations

    dot = build_dot(
        DEFAULT_ONTOLOGY,
        _plan(properties=("touches_shared_behavior",)),
        derivations,
        moment=MOMENT,
    )
    undeclared = {node for edge in _edges(dot) for node in edge} - _declared_nodes(dot)
    travelled = [line for line in dot.splitlines() if "b34700" in line]

    assert not undeclared, undeclared
    assert any(
        '"scope:one_line" -> "prop:trivial"' in line for line in travelled
    ), "the scope row derive() returned is not drawn as travelled"


def test_every_edge_endpoint_is_a_declared_node():
    plan = _plan(
        selected=(
            ("10", "inspect-repository", "code_change_requires_repository_context"),
            ("110", "report-result", "every_harness_run_reports_outcome"),
        ),
        blocked=(("run-broad-tests", "no_shared_or_cross_module_fact"),),
    )
    derivation = Derivation(
        request_property="trivial",
        source="scope(req, one_line)",
        path=("one_line", "trivial"),
    )

    dot = build_dot(DEFAULT_ONTOLOGY, plan, (derivation,), moment=MOMENT)
    edges = _edges(dot)
    declared = _declared_nodes(dot)

    # Guard first: "every endpoint is declared" is vacuously true of a graph
    # with no edges, which is what a broken renderer emits.
    assert len(edges) > 40, len(edges)
    undeclared = {node for edge in edges for node in edge} - declared
    assert not undeclared, undeclared


def test_the_graph_never_draws_a_rule_the_selector_did_not_return():
    # needs_plan and needs_broad_tests live only inside selector.RULES and are
    # never returned to a caller. Drawing them would put a second copy of the
    # rules in a renderer with nothing keeping the two in sync.
    dot = build_dot(
        DEFAULT_ONTOLOGY,
        _plan(selected=(("30", "create-implementation-plan", "risk_or_scope_requires_explicit_plan"),)),
        moment=MOMENT,
    )

    assert "needs_plan" not in dot
    assert "needs_broad_tests" not in dot
    assert "risk_or_scope_requires_explicit_plan" in dot, "the reason it did return"


def test_the_written_graph_lands_directly_in_the_directory_it_was_given(tmp_path: Path):
    # The directory takes no variation: no mkdtemp-style subdirectory, no
    # per-run nesting. Only the filename carries the timestamp.
    target = write_graph(tmp_path, DEFAULT_ONTOLOGY, _plan(), moment=MOMENT)

    assert target.parent == tmp_path
    assert target.name == graph_filename(MOMENT)
    assert [path.name for path in tmp_path.iterdir()] == [target.name]
    assert target.read_text(encoding="utf-8").startswith("// Generated by")


def test_the_written_graph_carries_the_bytes_the_renderer_produced(tmp_path: Path):
    # read_bytes, not read_text: universal newlines fold CRLF back to LF before
    # any assertion sees it, which is why forcing this write to CRLF left the
    # whole suite green. The neighbouring test reads text and is about where the
    # file lands; this one is about what is in it.
    #
    # What this can observe is asymmetric, and the asymmetry is the point.
    # Removing `newline="\n"` is a no-op on POSIX, so on a POSIX cell this test
    # cannot go red for that; the Windows cell is the observer for a removal,
    # and the mutation table's `graph-line-ending` entry is the POSIX proxy,
    # flipping the setting to CRLF rather than deleting it.
    target = write_graph(tmp_path, DEFAULT_ONTOLOGY, _plan(), moment=MOMENT)

    payload = target.read_bytes()

    assert b"\r" not in payload, "the platform's newline translation reached the file"
    assert payload.endswith(b"}\n"), "the file does not end in the terminator it was written with"
    # Not vacuous: a one-line `}\n` file satisfies both checks above for free.
    # The bundled TBox renders 149 newlines today, so the floor is not a bound
    # this graph approaches -- it is there to fail a file that stopped being one.
    assert payload.count(b"\n") > 40, "a graph this short is not the graph build_dot renders"


def test_a_carriage_return_in_the_source_never_reaches_the_file_raw(tmp_path: Path):
    # `source` is the one string reaching _escape that nothing validates: the
    # CLI passes --ontology through verbatim and CR is legal in a POSIX
    # filename. Every other term the CLI can put here is pattern-checked first
    # -- a direct importer can still hand a SelectedSkill an unvalidated
    # reason, which this escaping now covers too.
    #
    # Bytes, and lines split on the byte the writer used, so the CR is still in
    # the haystack when the assertions run -- read_text folds it away, and
    # str.splitlines() would cut the label in half around it.
    target = write_graph(
        tmp_path, DEFAULT_ONTOLOGY, _plan(), moment=MOMENT, source="/tmp/o\rdd.json"
    )

    payload = target.read_bytes()
    (label,) = [
        line.decode("utf-8")
        for line in payload.split(b"\n")
        if b"agent-workflows harness run" in line
    ]

    assert b"\r" not in payload, "a CR in --ontology reached the graph as a raw byte"
    # The absence above is satisfied for free by an _escape that drops the
    # character rather than escaping it, and by one that escapes it before the
    # backslash. Round-tripping is what makes it say something: measured, this
    # is the only assertion here that fails either mutant.
    assert "ontology: /tmp/o\rdd.json" in _unescape(label), "the escaping is not invertible"


def test_an_existing_graph_file_is_refused_rather_than_clobbered(tmp_path: Path):
    # The filename is fully predictable and the default directory is the
    # world-writable system temp, so an exclusive create is what keeps a
    # pre-planted symlink from redirecting the write.
    (tmp_path / graph_filename(MOMENT)).write_text("original", encoding="utf-8")

    with pytest.raises(FileExistsError):
        write_graph(tmp_path, DEFAULT_ONTOLOGY, _plan(), moment=MOMENT)

    assert (tmp_path / graph_filename(MOMENT)).read_text(encoding="utf-8") == "original"


def test_a_quote_in_a_label_cannot_break_out_of_the_dot_string():
    dot = build_dot(DEFAULT_ONTOLOGY, _plan(), moment=MOMENT, source='/tmp/o"dd\\path.json')

    (label,) = [line for line in dot.splitlines() if "agent-workflows harness run" in line]
    # Both characters escaped, and the string still closes: counting quotes
    # with the escaped ones removed is what distinguishes "escaped" from
    # "emitted raw and happens to look balanced".
    assert '\\"' in label and "\\\\" in label
    assert re.sub(r"\\.", "", label).count('"') == 2
