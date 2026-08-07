from __future__ import annotations

from .facts import format_fact_lines
from .models import BlockedSkill, RequestFacts, SelectedSkill, SkillPlan
from .ontology import DEFAULT_ONTOLOGY, Ontology
from .registry import (
    BLOCKING_REASON_BY_ID,
    MANDATORY_SKILL_CLASSES,
    PLANNED_SKILL_CLASSES,
    REASON_BY_CODE,
    SELECTION_REASON_BY_ID,
    SKILL_BY_ID,
    SKILL_CODE_BY_ID,
    SKILL_ID_BY_CODE,
)


#: Skill classes the rules reference directly, because their selection reason
#: depends on the request rather than on the skill.
_FOCUSED_TEST_CLASS = "FocusedTestSkill"
_BROAD_TEST_CLASS = "BroadTestSkill"
_REPORT_CLASS = "ReportSkill"


RULES = """
.decl request(req: symbol)
.decl request_type(req: symbol, typ: symbol)
.decl property(req: symbol, prop: symbol)
.decl sub_class_of(sub: int32, sup: int32)
.decl skill_type(skill: int32, cls: int32)
.decl skill_isa(skill: int32, cls: int32)
.decl skill_order(skill: int32, ord: int32)
.decl selection_reason(skill: int32, reason: int32)
.decl blocking_reason(skill: int32, reason: int32)
.decl mandatory_class(cls: int32)
.decl planned_class(cls: int32)
.decl needs_plan(req: symbol)
.decl needs_broad_tests(req: symbol)
.decl selected_skill(order: int32, skill: int32, reason: int32)
.decl blocked_skill(skill: int32, reason: int32)

skill_isa(S, C) :- skill_type(S, C).
skill_isa(S, Sup) :- skill_isa(S, C), sub_class_of(C, Sup).

needs_plan(Req) :- property(Req, "non_trivial").
needs_plan(Req) :- property(Req, "multi_file").
needs_plan(Req) :- property(Req, "external_service").
needs_plan(Req) :- property(Req, "touches_shared_behavior").

needs_broad_tests(Req) :- property(Req, "touches_shared_behavior").
needs_broad_tests(Req) :- property(Req, "multi_file").
needs_broad_tests(Req) :- property(Req, "external_service").

selected_skill(O, S, R) :-
    request_type(Req, "code_change"),
    mandatory_class(C),
    skill_isa(S, C),
    skill_order(S, O),
    selection_reason(S, R).

selected_skill(O, S, R) :-
    request_type(Req, "code_change"),
    needs_plan(Req),
    planned_class(C),
    skill_isa(S, C),
    skill_order(S, O),
    selection_reason(S, R).

selected_skill(O, S, 6) :-
    request_type(Req, "code_change"),
    !property(Req, "docs_only"),
    skill_isa(S, {focused}),
    skill_order(S, O).

selected_skill(O, S, 12) :-
    request_type(Req, "code_change"),
    property(Req, "docs_only"),
    skill_isa(S, {focused}),
    skill_order(S, O).

selected_skill(O, S, 7) :-
    request_type(Req, "code_change"),
    needs_broad_tests(Req),
    skill_isa(S, {broad}),
    skill_order(S, O).

selected_skill(O, S, 11) :-
    request(Req),
    skill_isa(S, {report}),
    skill_order(S, O).

blocked_skill(S, R) :-
    request_type(Req, "code_change"),
    !needs_plan(Req),
    planned_class(C),
    skill_isa(S, C),
    blocking_reason(S, R).

blocked_skill(S, 103) :-
    request_type(Req, "code_change"),
    !needs_broad_tests(Req),
    skill_isa(S, {broad}).

"""


class _ClassCodes:
    """Deterministic class name -> int32 mapping for the skill hierarchy."""

    def __init__(self, ontology: Ontology) -> None:
        self._code_by_name = {
            name: index + 1 for index, name in enumerate(sorted(ontology.classes()))
        }

    def __contains__(self, name: object) -> bool:
        return name in self._code_by_name

    def code(self, name: str) -> int:
        try:
            return self._code_by_name[name]
        except KeyError:
            raise ValueError(
                f"ontology does not declare the skill class {name!r} the selector requires"
            ) from None


def _catalog_lines(ontology: Ontology, classes: _ClassCodes) -> list[str]:
    """Emit the skill catalog: hierarchy, order, reasons, and policy classes."""

    lines: list[str] = []
    for sub, sup in ontology.sub_class_of:
        lines.append(f"sub_class_of({classes.code(sub)}, {classes.code(sup)}).")

    for skill_id, class_name in ontology.skill_class:
        code = SKILL_CODE_BY_ID.get(skill_id)
        if code is None:
            # An ontology may describe skills this harness does not register.
            continue
        lines.append(f"skill_type({code}, {classes.code(class_name)}).")

    for skill_id, code in sorted(SKILL_CODE_BY_ID.items()):
        lines.append(f"skill_order({code}, {SKILL_BY_ID[skill_id].order}).")

    for skill_id, reason in sorted(SELECTION_REASON_BY_ID.items()):
        lines.append(f"selection_reason({SKILL_CODE_BY_ID[skill_id]}, {reason}).")

    for skill_id, reason in sorted(BLOCKING_REASON_BY_ID.items()):
        lines.append(f"blocking_reason({SKILL_CODE_BY_ID[skill_id]}, {reason}).")

    for class_name in MANDATORY_SKILL_CLASSES:
        lines.append(f"mandatory_class({classes.code(class_name)}).")

    for class_name in PLANNED_SKILL_CLASSES:
        lines.append(f"planned_class({classes.code(class_name)}).")

    return lines


def build_program(facts: RequestFacts, ontology: Ontology | None = None) -> str:
    """Render the selector program: rules, the skill catalog, and request facts."""

    active = ontology or DEFAULT_ONTOLOGY
    classes = _ClassCodes(active)
    rules = RULES.format(
        focused=classes.code(_FOCUSED_TEST_CLASS),
        broad=classes.code(_BROAD_TEST_CLASS),
        report=classes.code(_REPORT_CLASS),
    )
    catalog = "\n".join(_catalog_lines(active, classes))
    return f"{rules}\n{catalog}\n{format_fact_lines(facts)}\n"


def select_plan(facts: RequestFacts, ontology: Ontology | None = None) -> SkillPlan:
    """Evaluate the skill selector with PyreWire and return the selected/blocked plan."""

    from pyrewire import BatchProgram

    with BatchProgram.from_string(build_program(facts, ontology)) as program:
        # program.optimize() is deliberately not called. On pyrewire 1.0.4 /
        # wirelog 0.53.0 the optimizer silently shifts head bindings for any
        # rule with four or more body atoms, which is exactly the shape of the
        # class-driven selection rules:
        #   selected_skill(O, S, R) :-
        #       request_type(...), mandatory_class(C), skill_isa(S, C),
        #       skill_order(S, O), selection_reason(S, R).
        # yields R = 0 instead of the stored reason. Reported as
        # semantic-reasoning/PyreWire#180 and pinned by
        # tests/test_selector_equivalence.py::
        #   test_optimizer_corrupts_head_bindings_on_four_atom_rules.
        program.load_all_facts()
        result = program.evaluate()
        try:
            selected_rows = (
                result.relation("selected_skill")
                if result.cardinality("selected_skill") > 0
                else []
            )
            blocked_rows = (
                result.relation("blocked_skill")
                if result.cardinality("blocked_skill") > 0
                else []
            )
        finally:
            result.close()

    selected = {
        row[1]: SelectedSkill(
            int(row[0]),
            SKILL_ID_BY_CODE[int(row[1])],
            REASON_BY_CODE[int(row[2])],
        )
        for row in selected_rows
    }
    blocked = {
        row[0]: BlockedSkill(SKILL_ID_BY_CODE[int(row[0])], REASON_BY_CODE[int(row[1])])
        for row in blocked_rows
    }
    return SkillPlan(
        request=facts,
        selected=tuple(sorted(selected.values(), key=lambda item: (item.order, item.skill_id))),
        blocked=tuple(sorted(blocked.values(), key=lambda item: item.skill_id)),
    )


def select_skills(facts: RequestFacts, ontology: Ontology | None = None) -> list[SelectedSkill]:
    """Evaluate the selector and return only selected skills for older callers."""

    return list(select_plan(facts, ontology).selected)
