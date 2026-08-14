from __future__ import annotations

import argparse
import json
import sys

from .facts import classify_request
from .models import RequestFacts
from .decision_log import append_decision_record
from .ontology import derive, load_ontology
from .serialization import plan_to_dict
from .selector import select_plan


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
        derivations = derive(args.touches, args.scope, ontology)
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
        print(
            "agent-workflows-harness: PyreWire/Wirelog selector failed. "
            "Ensure pyrewire is installed and WIRELOG_LIB points to libwirelog. "
            f"Cause: {exc}",
            file=sys.stderr,
        )
        return 2

    if args.decision_log:
        append_decision_record(args.decision_log, plan, derivations)

    if args.text:
        for item in derivations:
            print(f"    {item.request_property} <= {item.source} # {' -> '.join(item.path)}")
        for skill in plan.selected:
            print(f"{skill.order:03d} {skill.skill_id} # {skill.reason}")
        # Blocked skills carry no order, so they are labelled instead of being
        # given a fake step number. Omitting them made a plan that dropped a
        # gate look identical to a full plan.
        for skill in plan.blocked:
            print(f"blocked: {skill.skill_id} # {skill.reason}")
        return 0

    print(json.dumps(plan_to_dict(plan, derivations), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
