from __future__ import annotations

from .facts import format_fact_lines
from .models import BlockedSkill, RequestFacts, SelectedSkill, SkillPlan
from .registry import REASON_BY_CODE, SKILL_ID_BY_CODE


class HarnessError(Exception):
    """A harness failure that is not a caller input error.

    Deliberately not a `ValueError`: the CLI reports input errors with
    argparse's exit 2, and a rule defect must stay distinguishable from a
    request the caller can fix.
    """


class SelectorRuleConflictError(HarnessError):
    """Two Wirelog rules disagree about the same skill."""


RULES = """
.decl request(req: symbol)
.decl request_type(req: symbol, typ: symbol)
.decl property(req: symbol, prop: symbol)
.decl needs_plan(req: symbol)
.decl needs_broad_tests(req: symbol)
.decl selected_skill(order: int32, skill: int32, reason: int32)
.decl blocked_skill(skill: int32, reason: int32)

needs_plan(Req) :- property(Req, "non_trivial").
needs_plan(Req) :- property(Req, "multi_file").
needs_plan(Req) :- property(Req, "external_service").
needs_plan(Req) :- property(Req, "touches_shared_behavior").

needs_broad_tests(Req) :- property(Req, "touches_shared_behavior").
needs_broad_tests(Req) :- property(Req, "multi_file").
needs_broad_tests(Req) :- property(Req, "external_service").

selected_skill(10, 1, 1) :-
    request_type(Req, "code_change").

selected_skill(20, 2, 2) :-
    request_type(Req, "code_change").

selected_skill(30, 3, 3) :-
    request_type(Req, "code_change"),
    needs_plan(Req).

selected_skill(40, 4, 4) :-
    request_type(Req, "code_change"),
    needs_plan(Req).

selected_skill(50, 5, 5) :-
    request_type(Req, "code_change").

selected_skill(60, 6, 6) :-
    request_type(Req, "code_change"),
    !property(Req, "docs_only").

selected_skill(60, 6, 12) :-
    request_type(Req, "code_change"),
    property(Req, "docs_only").

selected_skill(70, 7, 7) :-
    request_type(Req, "code_change"),
    needs_broad_tests(Req).

selected_skill(80, 8, 8) :-
    request_type(Req, "code_change").

selected_skill(90, 9, 9) :-
    request_type(Req, "code_change").

selected_skill(100, 10, 10) :-
    request_type(Req, "code_change").

selected_skill(105, 12, 13) :-
    request_type(Req, "code_change").

selected_skill(110, 11, 11) :-
    request(Req).

blocked_skill(3, 101) :-
    request_type(Req, "code_change"),
    !needs_plan(Req).

blocked_skill(4, 102) :-
    request_type(Req, "code_change"),
    !needs_plan(Req).

blocked_skill(7, 103) :-
    request_type(Req, "code_change"),
    !needs_broad_tests(Req).

"""


def build_program(facts: RequestFacts) -> str:
    return f"{RULES}\n{format_fact_lines(facts)}\n"


def select_plan(facts: RequestFacts) -> SkillPlan:
    """Evaluate the skill selector with PyreWire and return the selected/blocked plan."""

    from pyrewire import BatchProgram

    with BatchProgram.from_string(build_program(facts)) as program:
        program.optimize()
        program.load_all_facts()
        result = program.evaluate()
        try:
            selected_rows = result.relation("selected_skill")
            blocked_rows = (
                result.relation("blocked_skill")
                if result.cardinality("blocked_skill") > 0
                else []
            )
        finally:
            result.close()

    return plan_from_rows(facts, selected_rows, blocked_rows)


def plan_from_rows(facts: RequestFacts, selected_rows, blocked_rows) -> SkillPlan:
    """Decode evaluated relation rows into a plan, or fail closed on a conflict.

    A plan must be a deterministic function of the facts. Keying the rows by
    skill code alone resolved two rules that disagree about the same skill by
    silently keeping whichever row the relation happened to yield last.
    """

    selected = {
        code: SelectedSkill(order, SKILL_ID_BY_CODE[code], REASON_BY_CODE[reason])
        for code, (order, reason) in _one_row_per_skill(
            ((int(row[1]), (int(row[0]), int(row[2]))) for row in selected_rows),
            "selected",
        ).items()
    }
    blocked = {
        code: BlockedSkill(SKILL_ID_BY_CODE[code], REASON_BY_CODE[reason])
        for code, (reason,) in _one_row_per_skill(
            ((int(row[0]), (int(row[1]),)) for row in blocked_rows), "blocked"
        ).items()
    }
    return SkillPlan(
        request=facts,
        selected=tuple(sorted(selected.values(), key=lambda item: (item.order, item.skill_id))),
        blocked=tuple(sorted(blocked.values(), key=lambda item: item.skill_id)),
    )


def _one_row_per_skill(rows, relation: str) -> dict[int, tuple[int, ...]]:
    """Collapse identical rows per skill and reject disagreeing ones."""

    by_code: dict[int, set[tuple[int, ...]]] = {}
    for code, values in rows:
        by_code.setdefault(code, set()).add(values)

    conflicts = {code: values for code, values in by_code.items() if len(values) > 1}
    if conflicts:
        detail = "; ".join(
            f"{SKILL_ID_BY_CODE.get(code, f'skill_code_{code}')}: "
            + ", ".join(str(value) for value in sorted(values))
            for code, values in sorted(conflicts.items())
        )
        raise SelectorRuleConflictError(
            f"{relation} rules disagree about the same skill: {detail}"
        )
    return {code: next(iter(values)) for code, values in by_code.items()}


def select_skills(facts: RequestFacts) -> list[SelectedSkill]:
    """Evaluate the selector and return only selected skills for older callers."""

    return list(select_plan(facts).selected)
