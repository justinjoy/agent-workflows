from __future__ import annotations

import argparse
import json
import sys

from .facts import classify_request
from .models import RequestFacts
from .decision_log import append_decision_record, append_failure_record
from .ontology import DEFAULT_ONTOLOGY, derive, load_ontology
from .serialization import plan_to_dict
from .selector import HarnessError, SelectorRuleConflictError, select_plan


# Distinct from argparse's usage-error 2, so a caller can tell a dead runtime
# from bad input, and a rule defect from either.
EXIT_SELECTOR_UNAVAILABLE = 3
EXIT_RULE_CONFLICT = 4
EXIT_HARNESS_ERROR = 5
RUNTIME_MESSAGE = (
    "PyreWire/Wirelog runtime unavailable. Ensure pyrewire is installed and "
    "WIRELOG_LIB points to libwirelog."
)
CONFLICT_MESSAGE = (
    "Wirelog rules disagree about the same skill. The plan is not a "
    "deterministic function of the request facts; fix the rules."
)
HARNESS_MESSAGE = (
    "The harness failed before producing a plan. This is a defect in the "
    "harness itself, not in the request or the environment."
)
# One table so a kind and its exit code cannot drift apart.
EXIT_BY_KIND = {
    "selector_unavailable": EXIT_SELECTOR_UNAVAILABLE,
    "rule_conflict": EXIT_RULE_CONFLICT,
    "harness_error": EXIT_HARNESS_ERROR,
}
MESSAGE_BY_KIND = {
    "selector_unavailable": RUNTIME_MESSAGE,
    "rule_conflict": CONFLICT_MESSAGE,
    "harness_error": HARNESS_MESSAGE,
}
# Which kind each harness failure reaches the caller as. The kind tables above
# cannot enforce this on their own: they are keyed by kind, so a new
# HarnessError subclass added without an entry here trips none of them and
# arrives as `selector_unavailable`, sending an operator to check WIRELOG_LIB
# for a defect in the harness.
KIND_BY_EXCEPTION = {
    SelectorRuleConflictError: "rule_conflict",
}


def _fail(args: argparse.Namespace, kind: str, cause: str) -> int:
    """Report a run that produced no plan and return its exit code."""

    _emit_error(args, kind, MESSAGE_BY_KIND[kind], cause)
    return EXIT_BY_KIND[kind]


def _emit_error(args: argparse.Namespace, kind: str, message: str, cause: str) -> None:
    """Report a run that produced no plan on stdout, stderr, and the log.

    A caller that captures only stdout used to see an empty string here and
    could read it as "no plan" instead of "no answer". The document carries no
    `selected` key so that misreading fails loudly.

    `cause` is the raw exception text and may name absolute paths or the
    `WIRELOG_LIB` value. That is deliberate: this is a local developer CLI and
    the path is the actionable part of the diagnostic.
    """

    cause = " ".join(str(cause).split())
    print(f"{kind}: {message} Cause: {cause}", file=sys.stderr)
    if args.text:
        print(f"error: {kind} # {cause}")
    else:
        print(
            json.dumps(
                {"error": {"kind": kind, "message": message, "cause": cause}},
                indent=2,
                sort_keys=True,
            )
        )
    _record(args.decision_log, append_failure_record, kind, cause)


def _record(path: str | None, append, *record_args) -> None:
    """Append a durable record without letting the log break the run.

    An unwritable log path must not change the exit code or suppress output
    that was already produced. It is a trace, not the answer.
    """

    # Only an absent flag skips the record. An empty --decision-log value is a
    # caller mistake and must warn rather than drop the trace in silence.
    if path is None:
        return
    try:
        append(path, *record_args)
    except (OSError, ValueError) as exc:
        print(f"decision log unavailable: {path!r}: {exc}", file=sys.stderr)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Select agent workflow skills with PyreWire.")
    parser.add_argument("request", nargs="*", help="Natural language request to classify.")
    parser.add_argument(
        "--property",
        action="append",
        default=[],
        help="Explicit request fact property. Can be supplied multiple times.",
    )
    parser.add_argument(
        "--touches",
        action="append",
        default=[],
        metavar="SURFACE",
        help=(
            "ABox triple: a declared ontology surface this request touches. "
            "Request properties are inferred from the surface class hierarchy. "
            "Can be supplied multiple times."
        ),
    )
    parser.add_argument(
        "--scope",
        action="append",
        default=[],
        metavar="SCOPE",
        help="ABox triple: a declared ontology scope for this request.",
    )
    parser.add_argument(
        "--ontology",
        metavar="PATH",
        help="JSON TBox document replacing the bundled default ontology.",
    )
    parser.add_argument(
        "--print-ontology",
        action="store_true",
        help=(
            "Print the active TBox as JSON and exit without evaluating any "
            "facts. Honours --ontology; every other argument is ignored."
        ),
    )
    parser.add_argument(
        "--text",
        action="store_true",
        help="Print a compact text plan instead of JSON.",
    )
    parser.add_argument(
        "--decision-log",
        help="Append the selected/blocked decision record to a JSON Lines file.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _parser()
    args = parser.parse_args(argv)
    request_text = " ".join(args.request)
    try:
        ontology = load_ontology(args.ontology) if args.ontology else None
    except (OSError, ValueError) as exc:
        parser.error(str(exc))

    if args.print_ontology:
        # After the load, so an --ontology file that fails validation still
        # exits 2: a document that did not load cannot be printed. Before
        # derive(), so printing the vocabulary never needs the Wirelog runtime
        # -- the caller reaching for this is usually the one whose fact was
        # just rejected, and rejecting it again would be useless.
        #
        # A successful run that selects nothing. Callers are told to branch on
        # the exit code, so exit 0 no longer implies a plan; both shipped
        # contracts say so, and the document carries no `selected` key.
        if args.decision_log is not None:
            # f704f69 decided that a supplied --decision-log is never dropped
            # in silence. There is no selection to record here, so say that
            # rather than leave the caller believing a trace was written.
            print(
                "decision log not written: --print-ontology selects nothing to record",
                file=sys.stderr,
            )
        document = (ontology or DEFAULT_ONTOLOGY).to_dict()
        if args.text:
            # `relation: left -> right`, one row per line. No term can contain
            # a space, ':' or '>' -- ontology._TERM_PATTERN forbids them -- so
            # the line splits unambiguously. Relations in sorted order, so text
            # and JSON agree. This form is for reading and grepping; JSON is
            # the surface to parse.
            for relation in sorted(document):
                for left, right in document[relation]:
                    print(f"{relation}: {left} -> {right}")
        else:
            print(json.dumps(document, indent=2, sort_keys=True))
        return 0

    try:
        derivations = derive(args.touches, args.scope, ontology)
    except ValueError as exc:
        # An undeclared surface or scope is bad input, not a dead runtime. The
        # message names the relation to declare in but not the values it
        # accepts, and a supplied TBox controls how many there are, so point at
        # the flag that prints them rather than growing the message.
        #
        # This decorates every ValueError derive() raises. Today those are
        # exactly the two vocabulary errors in ontology.derive(); a third kind
        # would silently acquire a remedy that does not fit, so check here
        # before adding one.
        parser.error(f"{exc}; run --print-ontology to list the declared vocabulary")
    except Exception as exc:
        # Loading libwirelog fails here before the selector is ever reached.
        # Routing it to parser.error would exit 2 with empty stdout, which a
        # caller reads as "no plan" rather than "no runtime".
        return _fail(args, "selector_unavailable", str(exc))

    try:
        inferred = {item.request_property for item in derivations}

        if request_text or args.property or inferred:
            properties = (
                set(classify_request(request_text).properties) if request_text else set()
            )
            facts = RequestFacts.from_properties(
                properties.union(args.property).union(inferred)
            )
        else:
            facts = RequestFacts()
    except (OSError, ValueError) as exc:
        parser.error(str(exc))

    try:
        plan = select_plan(facts)
    except HarnessError as exc:
        # A harness defect is not a dead runtime, and it must not be reported
        # as one: the caller's remedy is to fix the harness, not the
        # environment. An unmapped subclass still gets a truthful kind rather
        # than borrowing the runtime message.
        kind = KIND_BY_EXCEPTION.get(type(exc), "harness_error")
        return _fail(args, kind, str(exc))
    except Exception as exc:
        return _fail(args, "selector_unavailable", str(exc))

    # Print the plan before recording it, so an unwritable log cannot suppress
    # a plan the selector already computed.
    if args.text:
        for item in derivations:
            print(f"    {item.request_property} <= {item.source} # {' -> '.join(item.path)}")
        for skill in plan.selected:
            print(f"{skill.order:03d} {skill.skill_id} # {skill.reason}")
        # A blocked skill never runs, so numbering it would assert a step that
        # does not execute. Omitting these lines left a dropped gate as an
        # unexplained gap in the step numbers.
        for skill in plan.blocked:
            print(f"blocked: {skill.skill_id} # {skill.reason}")
    else:
        print(json.dumps(plan_to_dict(plan, derivations), indent=2, sort_keys=True))

    _record(args.decision_log, append_decision_record, plan, derivations)
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
