from __future__ import annotations

import json
import os
import subprocess
import sys
from importlib.metadata import version
from pathlib import Path

from agent_workflows_harness.facts import classify_request
from agent_workflows_harness.models import RequestFacts
from agent_workflows_harness.selector import build_program, select_plan, select_skills


ROOT = Path(__file__).resolve().parents[1]


def _ids(facts: RequestFacts) -> list[str]:
    return [skill.skill_id for skill in select_skills(facts)]


def _subprocess_env() -> dict[str, str]:
    env = os.environ.copy()
    current = env.get("PYTHONPATH")
    src_path = str(ROOT / "src")
    env["PYTHONPATH"] = src_path if not current else f"{src_path}{os.pathsep}{current}"
    return env


def test_build_program_contains_request_facts():
    facts = RequestFacts.from_properties({"needs_tests", "multi_file"})

    program = build_program(facts)

    assert 'request("req").' in program
    assert 'property("req", "multi_file").' in program
    assert 'property("req", "needs_tests").' in program


def test_classify_request_defaults_to_conservative_non_trivial():
    facts = classify_request("Change the auth workflow and add tests")

    assert "non_trivial" in facts.properties
    assert "touches_shared_behavior" in facts.properties
    assert "needs_tests" in facts.properties


def test_classifier_uses_word_boundaries_and_canonical_risk():
    unrelated = classify_request("Capitalize the heading")
    conflicting = classify_request("A trivial refactor")

    assert "external_service" not in unrelated.properties
    assert "non_trivial" in unrelated.properties
    assert conflicting.properties >= {"non_trivial"}
    assert "trivial" not in conflicting.properties


def test_required_pyrewire_version_is_installed():
    installed = tuple(int(part) for part in version("pyrewire").split(".")[:3])

    assert installed >= (1, 0, 4)


def test_trivial_code_change_gets_small_plan_and_blocks_gates():
    plan = select_plan(RequestFacts.from_properties({"trivial"}))

    assert [skill.skill_id for skill in plan.selected] == [
        "inspect-repository",
        "classify-change-risk",
        "implement-atomic-change",
        "run-focused-tests",
        "report-result",
    ]
    assert "create-implementation-plan" in {skill.skill_id for skill in plan.blocked}
    assert "review-diff" in {skill.skill_id for skill in plan.blocked}


def test_non_trivial_shared_change_gets_review_and_broad_tests():
    selected = _ids(
        RequestFacts.from_properties(
            {"non_trivial", "touches_shared_behavior", "needs_tests"}
        )
    )

    assert selected == [
        "inspect-repository",
        "classify-change-risk",
        "create-implementation-plan",
        "critique-plan",
        "implement-atomic-change",
        "run-focused-tests",
        "run-broad-tests",
        "review-diff",
        "validate-final-design",
        "validate-final-risks",
        "report-result",
    ]


def test_docs_only_change_still_selects_implementation():
    plan = select_plan(RequestFacts.from_properties({"docs_only"}))

    assert [skill.skill_id for skill in plan.selected] == [
        "inspect-repository",
        "classify-change-risk",
        "implement-atomic-change",
        "run-focused-tests",
        "report-result",
    ]
    focused = next(skill for skill in plan.selected if skill.skill_id == "run-focused-tests")
    assert focused.reason == "documentation_change_requires_focused_validation"


def test_docs_only_policy_handles_risk_and_rejects_code_impact():
    planned_docs = RequestFacts.from_properties({"docs_only", "non_trivial"})
    multi_file_docs = RequestFacts.from_properties({"docs_only", "multi_file"})

    assert "create-implementation-plan" in _ids(planned_docs)
    assert "run-broad-tests" in _ids(multi_file_docs)
    for conflicting in ("external_service", "touches_shared_behavior"):
        try:
            RequestFacts.from_properties({"docs_only", conflicting})
        except ValueError as exc:
            assert "docs_only conflicts" in str(exc)
        else:  # pragma: no cover
            raise AssertionError(f"expected docs_only + {conflicting} to fail")


def test_docs_only_text_does_not_infer_code_impact_from_documented_subjects():
    requests = (
        "docs only: update GitHub installation instructions",
        "README only: document the public API",
        "documentation only: explain the auth workflow",
    )

    for request in requests:
        facts = classify_request(request)
        assert "docs_only" in facts.properties
        assert "external_service" not in facts.properties
        assert "touches_shared_behavior" not in facts.properties
        assert "implement-atomic-change" in _ids(facts)


def test_empty_facts_fail_closed_to_non_trivial_plan():
    facts = RequestFacts()

    assert facts.properties == frozenset({"non_trivial"})
    assert "create-implementation-plan" in _ids(facts)


def test_risk_facts_override_trivial_hint():
    facts = RequestFacts.from_properties({"trivial", "non_trivial"})

    assert facts.properties == frozenset({"non_trivial"})
    assert "create-implementation-plan" in _ids(facts)


def test_request_facts_reject_source_breaking_or_unknown_values():
    for properties in ({'bad"fact'}, {"unknown"}, {"line\nbreak"}):
        try:
            RequestFacts.from_properties(properties)
        except ValueError as exc:
            assert "unsupported request properties" in str(exc)
        else:  # pragma: no cover - explicit assertion keeps the error dependency-free
            raise AssertionError(f"expected invalid properties to fail: {properties!r}")

    try:
        RequestFacts(request_id='req". injected(). request("x')
    except ValueError as exc:
        assert "request_id" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("expected invalid request_id to fail")


def test_selected_and_blocked_skills_are_disjoint_and_complete():
    plan = select_plan(RequestFacts.from_properties({"trivial"}))
    selected = {skill.skill_id for skill in plan.selected}
    blocked = {skill.skill_id for skill in plan.blocked}

    assert selected.isdisjoint(blocked)
    assert selected | blocked == {
        "inspect-repository",
        "classify-change-risk",
        "create-implementation-plan",
        "critique-plan",
        "implement-atomic-change",
        "run-focused-tests",
        "run-broad-tests",
        "review-diff",
        "validate-final-design",
        "validate-final-risks",
        "report-result",
    }


def test_cli_emits_machine_readable_json():
    proc = subprocess.run(
        [
            sys.executable,
            "-m",
            "agent_workflows_harness.cli",
            "--property",
            "trivial",
        ],
        check=True,
        env=_subprocess_env(),
        text=True,
        capture_output=True,
    )

    payload = json.loads(proc.stdout)

    assert payload["request"]["properties"] == ["trivial"]
    assert payload["selected"][0]["skill_id"] == "inspect-repository"
    assert any(skill["skill_id"] == "review-diff" for skill in payload["blocked"])


def test_cli_appends_decision_record(tmp_path):
    log_path = tmp_path / "decisions.jsonl"

    subprocess.run(
        [
            sys.executable,
            "-m",
            "agent_workflows_harness.cli",
            "--property",
            "trivial",
            "--decision-log",
            str(log_path),
        ],
        check=True,
        env=_subprocess_env(),
        text=True,
        capture_output=True,
    )

    records = [json.loads(line) for line in log_path.read_text(encoding="utf-8").splitlines()]

    assert records[0]["event_type"] == "agent_workflow.skill_plan_selected"
    assert records[0]["plan"]["selected"][0]["skill_id"] == "inspect-repository"


def test_cli_rejects_unknown_property_without_running_wirelog():
    proc = subprocess.run(
        [
            sys.executable,
            "-m",
            "agent_workflows_harness.cli",
            "--property",
            'bad"fact',
        ],
        check=False,
        env=_subprocess_env(),
        text=True,
        capture_output=True,
    )

    assert proc.returncode == 2
    assert "unsupported request properties" in proc.stderr
    assert "Traceback" not in proc.stderr


def test_cli_accepts_docs_only_text_about_external_subjects():
    proc = subprocess.run(
        [
            sys.executable,
            "-m",
            "agent_workflows_harness.cli",
            "docs only: update GitHub installation instructions",
        ],
        check=True,
        env=_subprocess_env(),
        text=True,
        capture_output=True,
    )

    payload = json.loads(proc.stdout)

    assert payload["request"]["properties"] == ["docs_only"]
    assert any(
        skill["reason"] == "documentation_change_requires_focused_validation"
        for skill in payload["selected"]
    )
