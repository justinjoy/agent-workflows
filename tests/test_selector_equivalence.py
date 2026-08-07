from __future__ import annotations

import json
from pathlib import Path

import pytest

from agent_workflows_harness.models import RequestFacts
from agent_workflows_harness.ontology import DEFAULT_ONTOLOGY, Ontology
from agent_workflows_harness.selector import RULES, build_program, select_plan


GOLDEN = Path(__file__).parent / "data" / "selector_golden.json"


def _plan_rows(plan) -> dict:
    return {
        "properties": sorted(plan.request.properties),
        "selected": [[s.order, s.skill_id, s.reason] for s in plan.selected],
        "blocked": [[b.skill_id, b.reason] for b in plan.blocked],
    }


def _reclassify(skill_id: str, new_class: str) -> Ontology:
    """Return the default ontology with one skill moved to another class."""

    moved = tuple(
        (sid, new_class if sid == skill_id else cls)
        for sid, cls in DEFAULT_ONTOLOGY.skill_class
    )
    return Ontology(
        sub_class_of=DEFAULT_ONTOLOGY.sub_class_of,
        surface_class=DEFAULT_ONTOLOGY.surface_class,
        skill_class=moved,
        property_of_class=DEFAULT_ONTOLOGY.property_of_class,
        scope_property=DEFAULT_ONTOLOGY.scope_property,
    )


def test_every_valid_request_matches_the_pre_consolidation_plan():
    """The class-driven rules reproduce the per-skill rules exactly.

    The golden file was captured from the previous selector across every
    property combination `RequestFacts` accepts.
    """

    golden = json.loads(GOLDEN.read_text(encoding="utf-8"))
    plans = golden["plans"]
    cases = golden["cases"]
    assert len(cases) == 320

    mismatched = []
    for key, (plan_index, normalized) in cases.items():
        combo = set(key.split("|")) if key else set()
        expected = dict(plans[plan_index], properties=sorted(normalized.split("|")))
        if _plan_rows(select_plan(RequestFacts.from_properties(combo))) != expected:
            mismatched.append(key)

    assert mismatched == []


def test_rules_name_classes_and_never_individual_skills():
    """The catalog is data: no rule may mention a specific skill."""

    from agent_workflows_harness.registry import SKILLS

    named = [skill.skill_id for skill in SKILLS if skill.skill_id in RULES]

    assert named == []


def test_consolidation_reduced_the_rule_count():
    # 23 rules before: 4 needs_plan, 3 needs_broad_tests, 13 selected, 3 blocked.
    assert RULES.count(":-") == 17


def test_reclassifying_a_skill_changes_the_plan_without_touching_the_rules():
    """Membership in a mandatory class is data, not a rule."""

    trivial = RequestFacts.from_properties({"trivial"})
    baseline = {skill.skill_id for skill in select_plan(trivial).selected}
    assert "create-implementation-plan" not in baseline

    promoted = _reclassify("create-implementation-plan", "ReviewSkill")
    selected = {skill.skill_id for skill in select_plan(trivial, promoted).selected}

    # Now unconditionally selected, with no change to RULES.
    assert "create-implementation-plan" in selected


def test_demoting_a_skill_removes_it_from_every_plan():
    # TestSkill is an abstract parent: the rules reference only its
    # FocusedTestSkill and BroadTestSkill children, so nothing selects it.
    demoted = _reclassify("validate-final-risks", "TestSkill")
    facts = RequestFacts.from_properties({"non_trivial"})

    selected = {skill.skill_id for skill in select_plan(facts, demoted).selected}

    assert "validate-final-risks" not in selected
    assert "review-diff" in selected


def test_build_program_still_emits_request_facts():
    program = build_program(RequestFacts.from_properties({"needs_tests", "multi_file"}))

    assert 'request("req").' in program
    assert 'property("req", "multi_file").' in program


def test_build_program_rejects_an_ontology_missing_a_required_class():
    incomplete = Ontology(
        sub_class_of=(("ContextSkill", "Skill"),),
        surface_class=(),
        skill_class=(("inspect-repository", "ContextSkill"),),
        property_of_class=(),
        scope_property=(),
    )

    with pytest.raises(ValueError, match="does not declare the skill class"):
        build_program(RequestFacts.from_properties({"trivial"}), incomplete)


def test_optimizer_corrupts_head_bindings_on_four_atom_rules():
    """Pins the upstream defect that forces select_plan to skip optimize().

    On pyrewire 1.0.4 / wirelog 0.53.0, a rule with four or more body atoms
    comes back with its head bindings shifted by one from the fourth atom
    onward, leaving the last one zero. Reported as
    semantic-reasoning/PyreWire#180. When this test fails, the optimizer was
    fixed and `select_plan` should call `optimize()` again.
    """

    from pyrewire import BatchProgram

    program_text = """
.decl typ(s: int32, c: int32)
.decl mand(c: int32)
.decl ord(s: int32, o: int32)
.decl rsn(s: int32, r: int32)
.decl out(o: int32, s: int32, r: int32)
out(O, S, R) :- mand(C), typ(S, C), ord(S, O), rsn(S, R).
typ(1, 5).
mand(5).
ord(1, 10).
rsn(1, 7).
"""

    def run(optimize: bool) -> list[tuple[int, ...]]:
        with BatchProgram.from_string(program_text) as program:
            if optimize:
                program.optimize()
            program.load_all_facts()
            result = program.evaluate()
            try:
                rows = sorted(
                    {tuple(int(value) for value in row) for row in result.relation("out")}
                )
            finally:
                result.close()
        return rows

    assert run(optimize=False) == [(10, 1, 7)]
    if run(optimize=True) == run(optimize=False):
        pytest.fail(
            "pyrewire optimizer no longer corrupts head bindings; "
            "re-enable program.optimize() in select_plan"
        )
