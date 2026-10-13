from __future__ import annotations

import json
import shlex

import pytest

from agent_workflows_harness import cli
from agent_workflows_harness.models import RequestFacts
from agent_workflows_harness.ontology import DEFAULT_ONTOLOGY, Ontology, derive
from agent_workflows_harness.ontology_packs import (
    BUILTIN_PACKS, OntologyPack, compose_ontology, load_pack,
)
from agent_workflows_harness.selector import select_plan
from agent_workflows_harness.serialization import plan_to_dict


def pack(pack_id="repo", requires=(), source="repo.json", **relations):
    return OntologyPack.from_dict({"id": pack_id, "schema_version": 1,
        "requires": list(requires), "ontology": relations}, source=source)


def evaluated(names, touches, scopes=()):
    composition = compose_ontology([load_pack(name) for name in names])
    derivations = derive(touches, scopes, composition.ontology)
    facts = RequestFacts.from_properties({item.request_property for item in derivations})
    return composition, derivations, select_plan(facts)


@pytest.mark.parametrize("name,surface,prop,skill,order,reason", [
    ("security", "secret_handling", "security_risk", "validate-security", 71, "security_risk_requires_security_validation"),
    ("data-change", "schema_migration", "data_change_risk", "validate-data-change", 72, "data_change_risk_requires_data_validation"),
    ("deployment", "deployment_manifest", "deployment_risk", "validate-deployment", 73, "deployment_risk_requires_deployment_validation"),
])
def test_domain_surface_selects_its_validation_even_for_one_line(name, surface, prop, skill, order, reason):
    _, _, result = evaluated([name], [surface], ["one_line"])
    assert result.request.properties == {prop, "non_trivial"}
    selected = {row.skill_id: (row.order, row.reason) for row in result.selected}
    assert selected[skill] == (order, reason)
    assert set(selected) & {"validate-security", "validate-data-change", "validate-deployment"} == {skill}
    assert {"create-implementation-plan", "critique-plan", "run-broad-tests"} <= selected.keys()
    assert not result.blocked


def test_all_domains_select_once_in_order_with_deterministic_plan():
    names = list(BUILTIN_PACKS)
    touches = ["secret_handling", "data_backfill", "runtime_configuration"]
    composition, derived, result = evaluated(names, touches)
    reversed_composition, reversed_derived, reversed_plan = evaluated(names[::-1] + names, touches[::-1])
    assert composition.to_dict() == reversed_composition.to_dict()
    assert composition.ontology.to_dict() == reversed_composition.ontology.to_dict()
    assert plan_to_dict(result, derived, composition) == plan_to_dict(reversed_plan, reversed_derived, reversed_composition)
    assert [(s.order, s.skill_id) for s in result.selected if 70 < s.order < 80] == [
        (71, "validate-security"), (72, "validate-data-change"), (73, "validate-deployment")], "all three domain validations must be selected once in order"
    assert len({s.skill_id for s in result.selected}) == len(result.selected)
    assert not result.blocked


def test_repository_extension_cross_pack_inheritance_and_multiple_providers():
    repo = pack(requires=["security"],
        surface_class=[["billing_secret", "BillingSecret"], ["billing_secret", "SecuritySurface"]],
        sub_class_of=[["BillingSecret", "SecuritySurface"], ["BillingSecret", "PersistenceSurface"]],
        property_of_class=[["SecuritySurface", "security_risk"]])
    composition = compose_ontology([repo, load_pack("security")])
    derived = derive(["billing_secret"], ontology=composition.ontology)
    result = select_plan(RequestFacts.from_properties({d.request_property for d in derived}))
    assert "validate-security" in {s.skill_id for s in result.selected}
    assert result.request.properties >= {"security_risk", "touches_shared_behavior"}
    security = next(d for d in derived if d.request_property == "security_risk")
    assert security.path == ("billing_secret", "SecuritySurface")
    assert [p.to_dict() for p in security.provenance] == [
        {"relation": "surface_class", "left": "billing_secret", "right": "SecuritySurface", "providers": ["pack:repo"]},
        {"relation": "property_of_class", "left": "SecuritySurface", "right": "security_risk", "providers": ["pack:repo", "pack:security"]}]
    inherited = next(d for d in derived if d.request_property == "touches_shared_behavior")
    assert [p.relation for p in inherited.provenance] == ["surface_class", "sub_class_of", "sub_class_of", "property_of_class"]
    assert inherited.provenance[-1].providers == ("base",)


def test_equal_duplicate_pack_definitions_normalize_relations_dependencies_and_sources():
    first = pack(requires=["security", "security"], source="a.json", surface_class=[["local", "SecuritySurface"], ["local", "SecuritySurface"]])
    second = pack(requires=["security"], source="b.json", surface_class=[["local", "SecuritySurface"]])
    one = compose_ontology([first, second, load_pack("security")])
    two = compose_ontology([load_pack("security"), second, first, first])
    assert one.to_dict() == two.to_dict()
    assert next(p for p in one.to_dict()["packs"] if p["id"] == "repo")["sources"] == ["a.json", "b.json"]


def test_conflicting_id_is_rejected_in_both_orders_with_both_sources():
    a = pack(source="a.json", surface_class=[["a", "DocSurface"]])
    b = pack(source="b.json", surface_class=[["b", "DocSurface"]])
    for candidates in ([a, b], [b, a]):
        with pytest.raises(ValueError, match="conflicting definitions.*repo.*a.json.*b.json"):
            compose_ontology(candidates)


@pytest.mark.parametrize("change,fragment", [
    ({"schema_version": True}, "unsupported schema_version"),
    ({"schema_version": 2}, "unsupported schema_version"),
    ({"schema_version": "1"}, "unsupported schema_version"),
    ({"id": "bad id"}, "pack id"),
    ({"requires": "security"}, "requires"),
    ({"requires": [1]}, "requires"),
    ({"ontology": {"surface_class": {"x": "Surface"}}}, "list of pairs"),
    ({"ontology": {"surface_class": [["x", "bad class"]]}}, "malformed"),
    ({"ontology": {"unknown_relation": []}}, "only TBox relations"),
    ({"ontology": {"property_of_class": [["Surface", "invented"]]}}, "unsupported request property"),
    ({"ontology": {"scope_property": [["scope", "invented"]]}}, "unsupported request property"),
    ({"unexpected": []}, "exactly"),
])
def test_pack_schema_rejects_bad_input_with_source(change, fragment):
    data = {"id": "repo", "schema_version": 1, "requires": [], "ontology": {}}
    data.update(change)
    with pytest.raises(ValueError, match="source.json: .*" + fragment):
        OntologyPack.from_dict(data, source="source.json")


def test_missing_and_cyclic_dependencies_are_explicit_errors():
    with pytest.raises(ValueError, match="repo.*repo.json.*missing pack 'security'"):
        compose_ontology([pack(requires=["security"])])
    with pytest.raises(ValueError, match="dependency cycle.*a.*a.json.*b.*b.json"):
        compose_ontology([pack("a", ["b"], "a.json"), pack("b", ["a"], "b.json")])
    with pytest.raises(ValueError, match="dependency cycle"):
        compose_ontology([pack(requires=["repo"])])


def test_final_union_rejects_cycles_and_undeclared_classes_with_sources():
    a = pack("a", source="a.json", sub_class_of=[["A", "B"]])
    b = pack("b", source="b.json", sub_class_of=[["B", "A"]])
    with pytest.raises(ValueError, match="a.json.*b.json.*contains a cycle"):
        compose_ontology([a, b])
    with pytest.raises(ValueError, match="repo.json.*undeclared classes.*Missing"):
        compose_ontology([pack(surface_class=[["local", "Missing"]])])


def test_custom_base_is_replaced_not_augmented_with_implicit_default():
    base = Ontology.from_dict({"sub_class_of": [["Custom", "Root"]], "surface_class": [["local", "Custom"]]})
    composition = compose_ontology([load_pack("security")], base, base_source="base.json")
    assert "readme" not in composition.ontology.individuals()
    assert {"local", "secret_handling"} <= composition.ontology.individuals()
    assert composition.to_dict()["base"] == {"provider": "base", "source": "base.json"}
    # The base is not an implicitly available dependency pack.
    with pytest.raises(ValueError, match="missing pack 'base'"):
        compose_ontology([pack(requires=["base"])], base)


def test_docs_and_domain_code_are_classified_without_false_docs_only():
    composition, derived, _ = evaluated(BUILTIN_PACKS, ["readme"])
    assert {d.request_property for d in derived} == {"docs_only"}
    _, mixed, mixed_plan = evaluated(BUILTIN_PACKS, ["readme", "secret_handling"])
    assert "docs_only" not in {d.request_property for d in mixed}
    assert "validate-security" in {s.skill_id for s in mixed_plan.selected}
    dual = compose_ontology([load_pack("security"), pack(surface_class=[["secret_handling", "DocSurface"]])])
    dual_derived = derive(["secret_handling"], ontology=dual.ontology)
    assert {d.request_property for d in dual_derived} == {"security_risk"}
    assert not {s.skill_id for s in select_plan(RequestFacts.from_properties({"docs_only"})).selected} & {
        "validate-security", "validate-data-change", "validate-deployment"}
    for risk in ("security_risk", "data_change_risk", "deployment_risk"):
        with pytest.raises(ValueError, match="docs_only conflicts"):
            RequestFacts.from_properties({"docs_only", risk})


def test_derivation_choice_does_not_depend_on_wirelog_row_order(monkeypatch):
    import pyrewire
    ontology = compose_ontology([pack(
        sub_class_of=[["A", "Root"], ["B", "Root"]],
        surface_class=[["local", "A"], ["local", "B"]],
        property_of_class=[["A", "security_risk"], ["B", "security_risk"]])]).ontology
    from agent_workflows_harness.ontology import _Symbols
    symbols = _Symbols(ontology)
    rows = [(symbols.code("security_risk"), symbols.code(cls), symbols.code("local")) for cls in ("A", "B")]

    class Result:
        def cardinality(self, name):
            return len(rows) if name == "derived_surface_property" else 0
        def relation(self, name):
            return rows
        def close(self):
            pass
    class Program:
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def optimize(self): pass
        def load_all_facts(self): pass
        def evaluate(self): return Result()
    monkeypatch.setattr(pyrewire.BatchProgram, "from_string", lambda _: Program())
    first = derive(["local"], ontology=ontology)
    rows.reverse()
    assert derive(["local"], ontology=ontology) == first
    assert first[0].path == ("local", "A")


def test_cli_composition_roundtrip_log_graph_and_unknown_vocabulary_hint(tmp_path, capsys):
    log = tmp_path / "decisions.jsonl"
    argv = ["--ontology-pack", "security", "--ontology-pack", "deployment"]
    assert cli.main([*argv, "--touches", "secret_handling", "--decision-log", str(log), "--graph", str(tmp_path)]) == 0
    captured = capsys.readouterr()
    result = json.loads(captured.out)
    assert json.loads(log.read_text())["plan"] == result
    assert {p["id"] for p in result["ontology_composition"]["packs"]} == {"security", "deployment"}
    dot = next(tmp_path.glob("*.dot")).read_text()
    assert 'tooltip="providers: pack:security"' in dot
    assert "builtin:security" in dot
    assert "security_risk_requires_security_validation" in dot
    assert cli.main([*argv, "--print-ontology"]) == 0
    document = json.loads(capsys.readouterr().out)
    assert set(document) == set(DEFAULT_ONTOLOGY.to_dict())
    assert Ontology.from_dict(document) == compose_ontology([load_pack("security"), load_pack("deployment")]).ontology
    with pytest.raises(SystemExit) as error:
        cli.main([*argv, "--touches", "not_declared"])
    assert error.value.code == 2
    captured = capsys.readouterr()
    assert not captured.out
    hint = captured.err.rsplit("; run ", 1)[1].split(" to list the declared vocabulary")[0]
    assert cli.main(shlex.split(hint)) == 0
    assert json.loads(capsys.readouterr().out) == document


def test_cli_local_extension_custom_base_and_hostile_source_paths(tmp_path, capsys):
    base_path = tmp_path / 'custom base.json'
    base_path.write_text(json.dumps({"sub_class_of": [["Local", "Surface"]]}))
    path = tmp_path / 'repo pack.json'
    path.write_text(json.dumps({"id": "repo", "schema_version": 1, "requires": ["security"],
        "ontology": {"surface_class": [["local_secret", "SecuritySurface"]]}}))
    argv = ["--ontology", str(base_path), "--ontology-pack", str(path), "--ontology-pack", "security"]
    assert cli.main([*argv, "--touches", "local_secret", "--graph", str(tmp_path)]) == 0
    result = json.loads(capsys.readouterr().out)
    assert "validate-security" in {s["skill_id"] for s in result["selected"]}
    assert result["ontology_composition"]["base"]["source"] == str(base_path)
    dot = next(tmp_path.glob("*.dot")).read_text()
    assert 'repo pack.json' in dot
    assert 'tooltip="providers: pack:repo"' in dot
    with pytest.raises(SystemExit):
        cli.main([*argv, "--touches", "invalid"])
    error = capsys.readouterr().err
    hint = error.rsplit("; run ", 1)[1].split(" to list the declared vocabulary")[0]
    assert cli.main(shlex.split(hint)) == 0
    document = json.loads(capsys.readouterr().out)
    assert "readme" not in Ontology.from_dict(document).individuals()


def test_list_and_print_are_runtime_free_queries_with_no_writes(tmp_path, capsys, monkeypatch):
    def fail(*args):
        raise AssertionError("query should not infer or select")
    monkeypatch.setattr(cli, "derive", fail)
    monkeypatch.setattr(cli, "select_plan", fail)
    for flag in ("--list-ontology-packs", "--print-ontology"):
        log = tmp_path / "unused.jsonl"
        assert cli.main([flag, "--ontology-pack", "security", "--graph", str(tmp_path), "--decision-log", str(log)]) == 0
        captured = capsys.readouterr()
        assert "selected" not in json.loads(captured.out)
        assert "graph not written" in captured.err and "decision log not written" in captured.err
        assert not log.exists() and not list(tmp_path.glob("*.dot"))
    assert cli.main(["--list-ontology-packs"]) == 0
    data = json.loads(capsys.readouterr().out)
    assert {p["id"] for p in data["packs"]} == {"security", "data-change", "deployment"}
    assert next(p for p in data["packs"] if p["id"] == "security")["surfaces"] == ["authorization_policy", "personal_data_flow", "secret_handling"]
    with pytest.raises(SystemExit) as error:
        cli.main(["--list-ontology-packs", "--print-ontology"])
    assert error.value.code == 2


def test_no_pack_tbox_and_whole_plan_contract_unchanged(capsys):
    assert compose_ontology([]).ontology is DEFAULT_ONTOLOGY
    assert cli.main(["--touches", "session_module", "--scope", "one_line"]) == 0
    result = json.loads(capsys.readouterr().out)
    assert set(result) == {"request", "selected", "blocked", "derived"}
    assert result["request"]["properties"] == ["non_trivial", "touches_shared_behavior"]
    assert result["blocked"] == []
    assert [s["skill_id"] for s in result["selected"]] == [
        "inspect-repository", "classify-change-risk", "create-implementation-plan", "critique-plan",
        "implement-atomic-change", "run-focused-tests", "run-broad-tests", "review-diff",
        "validate-final-design", "validate-final-risks", "commit-atomic-change", "report-result"]
    assert result["derived"] == [
        {"from": "touches(req, session_module)", "path": "session_module -> AuthSurface -> SharedBehavior", "property": "touches_shared_behavior"},
        {"from": "scope(req, one_line)", "path": "one_line -> trivial", "property": "trivial"}]


def test_domain_risks_override_explicit_trivial_hints():
    for risk in ("security_risk", "data_change_risk", "deployment_risk"):
        facts = RequestFacts.from_properties({risk, "trivial"})
        assert facts.properties == {risk, "non_trivial"}, "domain risk must override trivial"


def test_scope_and_surface_with_same_name_keep_both_proofs():
    composition = compose_ontology([load_pack("security"), pack(
        scope_property=[["secret_handling", "security_risk"]])])
    derived = derive(["secret_handling"], ["secret_handling"], composition.ontology)
    proofs = [d for d in derived if d.request_property == "security_risk"]
    assert len(proofs) == 2
    assert {p.provenance[-1].relation for p in proofs} == {"scope_property", "property_of_class"}


def test_invalid_pack_files_fail_before_printing_or_selecting(tmp_path, capsys):
    bad = tmp_path / "bad.json"
    for text in ('{', '{"id": "bad"}', '{"id":"bad","schema_version":2,"requires":[],"ontology":{}}'):
        bad.write_text(text)
        for query in ([], ["--print-ontology"], ["--list-ontology-packs"]):
            with pytest.raises(SystemExit) as error:
                cli.main(["--ontology-pack", str(bad), *query])
            assert error.value.code == 2
            captured = capsys.readouterr()
            assert not captured.out
            assert str(bad) in captured.err


def test_packs_are_recorded_for_core_only_requests_and_text_mode(capsys):
    assert cli.main(["--ontology-pack", "security", "--touches", "readme"]) == 0
    data = json.loads(capsys.readouterr().out)
    assert data["ontology_composition"]["packs"][0]["id"] == "security"
    assert data["derived"][0]["provenance"] == [
        {"relation": "surface_class", "left": "readme", "right": "DocSurface", "providers": ["base"]}]
    assert cli.main(["--ontology-pack", "security", "--touches", "readme", "--text"]) == 0
    assert "ontology_composition:" in capsys.readouterr().out
    assert cli.main(["--list-ontology-packs", "--text"]) == 0
    assert "security: schema 1; surfaces: authorization_policy, personal_data_flow, secret_handling" in capsys.readouterr().out
