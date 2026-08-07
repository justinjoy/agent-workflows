from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from agent_workflows_harness.models import RequestFacts
from agent_workflows_harness.ontology import (
    DEFAULT_ONTOLOGY,
    Ontology,
    derive,
    derived_properties,
    load_ontology,
    subsumption_path,
)
from agent_workflows_harness.registry import SKILLS
from agent_workflows_harness.selector import select_skills
from agent_workflows_harness.serialization import plan_to_dict


ROOT = Path(__file__).resolve().parents[1]


def _subprocess_env() -> dict[str, str]:
    env = os.environ.copy()
    current = env.get("PYTHONPATH")
    src_path = str(ROOT / "src")
    env["PYTHONPATH"] = src_path if not current else f"{src_path}{os.pathsep}{current}"
    return env


def _run_cli(*argv: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-m", "agent_workflows_harness.cli", *argv],
        capture_output=True,
        text=True,
        env=_subprocess_env(),
        cwd=ROOT,
    )


def test_subclass_closure_derives_shared_behavior_without_the_keyword():
    # "session_module" contains no keyword the regex classifier knows; the
    # property comes from AuthSurface being subsumed by SharedBehavior.
    assert derived_properties(["session_module"]) == frozenset({"touches_shared_behavior"})


def test_derivation_reports_the_subsumption_path():
    (derivation,) = derive(["session_module"])

    assert derivation.request_property == "touches_shared_behavior"
    assert derivation.source == "touches(req, session_module)"
    assert derivation.path == ("session_module", "AuthSurface", "SharedBehavior")


def test_subsumption_path_is_the_shortest_chain():
    assert subsumption_path(DEFAULT_ONTOLOGY, "migration", "Surface") == (
        "migration",
        "PersistenceSurface",
        "SharedBehavior",
        "Surface",
    )


def test_scope_triples_derive_scope_properties():
    assert derived_properties([], ["one_line"]) == frozenset({"trivial"})
    assert derived_properties([], ["cross_module"]) == frozenset({"multi_file"})


def test_docs_only_requires_every_surface_to_be_documentation():
    assert "docs_only" in derived_properties(["readme", "changelog"])
    assert "docs_only" not in derived_properties(["readme", "auth_module"])


def test_external_service_surface_is_not_shared_behavior():
    properties = derived_properties(["github_api"])

    assert properties == frozenset({"external_service"})


def test_no_triples_derive_nothing():
    assert derive([], []) == ()


def test_unknown_surface_is_rejected():
    with pytest.raises(ValueError, match="unknown surface"):
        derive(["nonexistent_module"])


def test_unknown_scope_is_rejected():
    with pytest.raises(ValueError, match="unknown scope"):
        derive([], ["gigantic"])


def test_ontology_rejects_subclass_cycles():
    with pytest.raises(ValueError, match="cycle"):
        Ontology(
            sub_class_of=(("A", "B"), ("B", "A")),
            surface_class=(),
            skill_class=(),
            property_of_class=(),
            scope_property=(),
        )


def test_ontology_rejects_undeclared_classes():
    with pytest.raises(ValueError, match="undeclared classes"):
        Ontology(
            sub_class_of=(("A", "B"),),
            surface_class=(("thing", "C"),),
            skill_class=(),
            property_of_class=(),
            scope_property=(),
        )


def test_ontology_rejects_unsupported_request_properties():
    with pytest.raises(ValueError, match="unsupported request properties"):
        Ontology(
            sub_class_of=(("A", "B"),),
            surface_class=(),
            skill_class=(),
            property_of_class=(("A", "not_a_property"),),
            scope_property=(),
        )


def test_ontology_rejects_malformed_terms():
    with pytest.raises(ValueError, match="must start with a letter"):
        Ontology(
            sub_class_of=(("1bad", "B"),),
            surface_class=(),
            skill_class=(),
            property_of_class=(),
            scope_property=(),
        )


def test_default_ontology_classifies_every_registry_skill():
    classified = {skill_id for skill_id, _ in DEFAULT_ONTOLOGY.skill_class}

    assert classified == {skill.skill_id for skill in SKILLS}


def test_ontology_document_roundtrip(tmp_path: Path):
    path = tmp_path / "tbox.json"
    path.write_text(json.dumps(DEFAULT_ONTOLOGY.to_dict()), encoding="utf-8")

    assert load_ontology(path) == DEFAULT_ONTOLOGY


def test_load_ontology_rejects_invalid_json(tmp_path: Path):
    path = tmp_path / "tbox.json"
    path.write_text("{not json", encoding="utf-8")

    with pytest.raises(ValueError, match="not valid JSON"):
        load_ontology(path)


def test_load_ontology_rejects_unsupported_keys(tmp_path: Path):
    path = tmp_path / "tbox.json"
    path.write_text(json.dumps({"surprise": []}), encoding="utf-8")

    with pytest.raises(ValueError, match="unsupported keys"):
        load_ontology(path)


def test_custom_ontology_extends_the_vocabulary_without_code_changes():
    extended = Ontology(
        sub_class_of=DEFAULT_ONTOLOGY.sub_class_of,
        surface_class=DEFAULT_ONTOLOGY.surface_class + (("billing_ledger", "PersistenceSurface"),),
        skill_class=DEFAULT_ONTOLOGY.skill_class,
        property_of_class=DEFAULT_ONTOLOGY.property_of_class,
        scope_property=DEFAULT_ONTOLOGY.scope_property,
    )

    assert derived_properties(["billing_ledger"], [], extended) == frozenset(
        {"touches_shared_behavior"}
    )


def test_ontology_facts_select_the_gates_the_keyword_classifier_drops():
    inferred = derived_properties(["session_module"], ["one_line"])
    facts = RequestFacts.from_properties(inferred)

    selected = {skill.skill_id for skill in select_skills(facts)}

    # Concrete risk evidence still wins over the caller's "one line" hint.
    assert "trivial" not in facts.properties
    assert {"create-implementation-plan", "critique-plan", "run-broad-tests"} <= selected


def test_plan_to_dict_omits_derived_key_without_ontology_facts():
    from agent_workflows_harness.selector import select_plan

    payload = plan_to_dict(select_plan(RequestFacts.from_properties({"trivial"})))

    assert "derived" not in payload


def test_cli_reports_derived_facts_as_json():
    result = _run_cli("--touches", "session_module", "--scope", "one_line")

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    derived = {entry["property"]: entry for entry in payload["derived"]}

    assert derived["touches_shared_behavior"]["path"] == (
        "session_module -> AuthSurface -> SharedBehavior"
    )
    assert payload["blocked"] == []


def test_cli_rejects_unknown_surface():
    result = _run_cli("--touches", "nonexistent_module")

    assert result.returncode != 0
    assert "unknown surface" in result.stderr


def test_cli_combines_text_and_ontology_facts():
    result = _run_cli("add docs only", "--touches", "github_api")

    assert result.returncode != 0
    assert "docs_only conflicts" in result.stderr
