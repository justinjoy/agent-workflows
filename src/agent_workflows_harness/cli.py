from __future__ import annotations

import argparse
import json
import sys

from .facts import classify_request
from .models import RequestFacts
from .decision_log import append_decision_record, append_failure_record
from .ontology import derive, load_ontology
from .serialization import plan_to_dict
from .selector import select_plan


# Distinct from argparse's usage-error 2, so a caller can tell a dead runtime
# from bad input.
EXIT_SELECTOR_UNAVAILABLE = 3
RUNTIME_MESSAGE = (
    "PyreWire/Wirelog runtime unavailable. Ensure pyrewire is installed and "
    "WIRELOG_LIB points to libwirelog."
)


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

    try:
        derivations = derive(args.touches, args.scope, ontology)
    except ValueError as exc:
        # An undeclared surface or scope is bad input, not a dead runtime.
        parser.error(str(exc))
    except Exception as exc:
        # Loading libwirelog fails here before the selector is ever reached.
        # Routing it to parser.error would exit 2 with empty stdout, which a
        # caller reads as "no plan" rather than "no runtime".
        _emit_error(args, "selector_unavailable", RUNTIME_MESSAGE, str(exc))
        return EXIT_SELECTOR_UNAVAILABLE

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
    except Exception as exc:
        _emit_error(args, "selector_unavailable", RUNTIME_MESSAGE, str(exc))
        return EXIT_SELECTOR_UNAVAILABLE

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
