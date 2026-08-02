from __future__ import annotations

import argparse
import json
import sys

from .facts import classify_request
from .models import RequestFacts
from .decision_log import append_decision_record
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
        if request_text or args.property:
            properties = (
                set(classify_request(request_text).properties) if request_text else set()
            )
            facts = RequestFacts.from_properties(properties.union(args.property))
        else:
            facts = RequestFacts()
    except ValueError as exc:
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
        append_decision_record(args.decision_log, plan)

    if args.text:
        for skill in plan.selected:
            print(f"{skill.order:03d} {skill.skill_id} # {skill.reason}")
        return 0

    print(json.dumps(plan_to_dict(plan), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
