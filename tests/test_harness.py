from __future__ import annotations

import json
import os
import subprocess
import sys
from importlib.metadata import version
from pathlib import Path

from agent_workflows_harness import cli
from agent_workflows_harness.facts import classify_request
from agent_workflows_harness.models import RequestFacts
from agent_workflows_harness.ontology import derive
from agent_workflows_harness.registry import SKILL_BY_ID, SKILL_CODE_BY_ID
from agent_workflows_harness.selector import build_program, select_plan, select_skills


ROOT = Path(__file__).resolve().parents[1]


def _ids(facts: RequestFacts) -> list[str]:
    return [skill.skill_id for skill in select_skills(facts)]


def _steps(facts: RequestFacts) -> list[tuple[int, str, str]]:
    return [
        (skill.order, skill.skill_id, skill.reason)
        for skill in select_skills(facts)
    ]


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


def test_trivial_code_change_gets_review_consensus_and_commit_gates():
    plan = select_plan(RequestFacts.from_properties({"trivial"}))

    assert [skill.skill_id for skill in plan.selected] == [
        "inspect-repository",
        "classify-change-risk",
        "implement-atomic-change",
        "run-focused-tests",
        "review-diff",
        "validate-final-design",
        "validate-final-risks",
        "commit-atomic-change",
        "report-result",
    ]
    assert "create-implementation-plan" in {skill.skill_id for skill in plan.blocked}
    assert "review-diff" not in {skill.skill_id for skill in plan.blocked}


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
        "commit-atomic-change",
        "report-result",
    ]


def test_docs_only_change_still_selects_implementation():
    plan = select_plan(RequestFacts.from_properties({"docs_only"}))

    assert [skill.skill_id for skill in plan.selected] == [
        "inspect-repository",
        "classify-change-risk",
        "implement-atomic-change",
        "run-focused-tests",
        "review-diff",
        "validate-final-design",
        "validate-final-risks",
        "commit-atomic-change",
        "report-result",
    ]
    focused = next(skill for skill in plan.selected if skill.skill_id == "run-focused-tests")
    assert focused.reason == "documentation_change_requires_focused_validation"
    assert next(skill for skill in plan.selected if skill.skill_id == "review-diff").reason == (
        "every_code_change_requires_review"
    )
    assert next(
        skill for skill in plan.selected if skill.skill_id == "commit-atomic-change"
    ).reason == "every_code_change_requires_atomic_commit"


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


def test_commit_hint_is_compatible_but_commit_is_always_selected():
    without_hint = _ids(RequestFacts.from_properties({"docs_only"}))
    with_hint = _ids(RequestFacts.from_properties({"docs_only", "needs_commit"}))

    assert with_hint == without_hint
    assert "commit-atomic-change" in without_hint


def test_new_skill_keeps_existing_wirelog_codes_stable():
    assert SKILL_CODE_BY_ID["report-result"] == 11
    assert SKILL_CODE_BY_ID["commit-atomic-change"] == 12
    assert SKILL_BY_ID["commit-atomic-change"].order == 105
    assert SKILL_BY_ID["report-result"].order == 110


def test_every_change_uses_exact_review_consensus_commit_tail():
    common_tail = [
        (80, "review-diff", "every_code_change_requires_review"),
        (
            90,
            "validate-final-design",
            "every_code_change_requires_architect_validation",
        ),
        (
            100,
            "validate-final-risks",
            "every_code_change_requires_critic_validation",
        ),
        (105, "commit-atomic-change", "every_code_change_requires_atomic_commit"),
        (110, "report-result", "every_harness_run_reports_outcome"),
    ]
    cases = (
        (
            {"docs_only"},
            [
                (10, "inspect-repository", "code_change_requires_repository_context"),
                (20, "classify-change-risk", "code_change_requires_risk_classification"),
                (50, "implement-atomic-change", "code_change_requires_atomic_implementation"),
                (60, "run-focused-tests", "documentation_change_requires_focused_validation"),
            ],
        ),
        (
            {"trivial"},
            [
                (10, "inspect-repository", "code_change_requires_repository_context"),
                (20, "classify-change-risk", "code_change_requires_risk_classification"),
                (50, "implement-atomic-change", "code_change_requires_atomic_implementation"),
                (60, "run-focused-tests", "code_change_requires_focused_validation"),
            ],
        ),
        (
            {"non_trivial", "touches_shared_behavior", "needs_tests"},
            [
                (10, "inspect-repository", "code_change_requires_repository_context"),
                (20, "classify-change-risk", "code_change_requires_risk_classification"),
                (30, "create-implementation-plan", "risk_or_scope_requires_explicit_plan"),
                (40, "critique-plan", "planned_change_requires_plan_critique"),
                (50, "implement-atomic-change", "code_change_requires_atomic_implementation"),
                (60, "run-focused-tests", "code_change_requires_focused_validation"),
                (70, "run-broad-tests", "shared_or_cross_module_behavior_changed"),
            ],
        ),
    )

    for properties, prefix in cases:
        assert _steps(RequestFacts.from_properties(properties)) == prefix + common_tail


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
        "commit-atomic-change",
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
    assert any(skill["skill_id"] == "review-diff" for skill in payload["selected"])
    assert any(
        skill["skill_id"] == "commit-atomic-change" for skill in payload["selected"]
    )


def test_cli_text_mode_reports_blocked_skills_with_reasons():
    trivial = subprocess.run(
        [sys.executable, "-m", "agent_workflows_harness.cli", "--text", "--property", "trivial"],
        check=True,
        env=_subprocess_env(),
        text=True,
        capture_output=True,
    )
    planned = subprocess.run(
        [
            sys.executable,
            "-m",
            "agent_workflows_harness.cli",
            "--text",
            "--property",
            "non_trivial",
            "--property",
            "touches_shared_behavior",
        ],
        check=True,
        env=_subprocess_env(),
        text=True,
        capture_output=True,
    )

    lines = trivial.stdout.splitlines()
    blocked = [line for line in lines if line.startswith("blocked: ")]

    assert blocked == [
        "blocked: create-implementation-plan # risk_facts_do_not_require_explicit_plan",
        "blocked: critique-plan # no_plan_selected",
        "blocked: run-broad-tests # no_shared_or_cross_module_behavior_fact",
    ]
    # Selected steps keep their ordered numeric shape.
    assert lines[0] == "010 inspect-repository # code_change_requires_repository_context"
    # A plan that blocks nothing prints no blocked line at all.
    assert "blocked: " not in planned.stdout
    assert "create-implementation-plan" in planned.stdout


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


def _fail_selector(message: str):
    def _raise(facts):
        raise RuntimeError(message)

    return _raise


def test_cli_reports_selector_failure_on_stdout_as_json(capsys, monkeypatch, tmp_path):
    log_path = tmp_path / "decisions.jsonl"
    monkeypatch.setattr(cli, "select_plan", _fail_selector("libwirelog\nnot found"))

    code = cli.main(["--property", "trivial", "--decision-log", str(log_path)])
    captured = capsys.readouterr()
    payload = json.loads(captured.out)

    assert code == cli.EXIT_SELECTOR_UNAVAILABLE == 3
    assert payload["error"]["kind"] == "selector_unavailable"
    # Pin the documented message so docs/how-it-works.md cannot drift from it.
    assert payload["error"]["message"] == cli.RUNTIME_MESSAGE
    assert cli.RUNTIME_MESSAGE in (ROOT / "docs" / "how-it-works.md").read_text(
        encoding="utf-8"
    )
    # A dead runtime must not be readable as an empty plan.
    assert "selected" not in payload
    assert "blocked" not in payload
    # The cause is collapsed to one line so it cannot break a line-per-record reader.
    assert payload["error"]["cause"] == "libwirelog not found"
    assert "WIRELOG_LIB" in captured.err

    record = json.loads(log_path.read_text(encoding="utf-8").splitlines()[0])
    assert record["event_type"] == "agent_workflow.skill_plan_failed"
    assert record["error"]["kind"] == "selector_unavailable"


def test_cli_reports_selector_failure_in_text_mode(capsys, monkeypatch):
    monkeypatch.setattr(cli, "select_plan", _fail_selector("libwirelog\nnot found"))

    code = cli.main(["--text", "--property", "trivial"])
    captured = capsys.readouterr()

    assert code == cli.EXIT_SELECTOR_UNAVAILABLE
    assert captured.out.splitlines() == [
        "error: selector_unavailable # libwirelog not found"
    ]


def test_cli_reports_an_unloadable_runtime_from_the_ontology_step(capsys, monkeypatch):
    # Loading libwirelog fails inside derive(), before the selector runs. This
    # used to reach parser.error and exit 2 with empty stdout.
    def _raise(touches, scopes, ontology):
        raise OSError("Could not find libwirelog")

    monkeypatch.setattr(cli, "derive", _raise)

    code = cli.main(["--property", "trivial"])
    payload = json.loads(capsys.readouterr().out)

    assert code == cli.EXIT_SELECTOR_UNAVAILABLE
    assert payload["error"]["kind"] == "selector_unavailable"
    assert "selected" not in payload


def test_cli_keeps_undeclared_ontology_terms_an_input_error(capsys, monkeypatch):
    def _raise(touches, scopes, ontology):
        raise ValueError("unknown surface 'nope'")

    monkeypatch.setattr(cli, "derive", _raise)

    try:
        cli.main(["--touches", "nope"])
    except SystemExit as exc:
        assert exc.code == 2
    else:  # pragma: no cover
        raise AssertionError("expected an argparse usage error")

    assert capsys.readouterr().out == ""


def test_derive_without_abox_triples_does_not_need_the_wirelog_runtime(monkeypatch):
    monkeypatch.setitem(sys.modules, "pyrewire", None)

    assert derive((), ()) == ()


def test_an_unwritable_decision_log_never_suppresses_the_answer(capsys, tmp_path):
    blocker = tmp_path / "blocker.txt"
    blocker.write_text("not a directory", encoding="utf-8")
    unwritable = str(blocker / "sub" / "decisions.jsonl")

    plan_code = cli.main(["--property", "trivial", "--decision-log", unwritable])
    plan_output = capsys.readouterr()

    assert plan_code == 0
    assert json.loads(plan_output.out)["selected"]
    assert "decision log unavailable" in plan_output.err


def test_an_unwritable_decision_log_never_changes_the_failure_exit_code(
    capsys, monkeypatch, tmp_path
):
    blocker = tmp_path / "blocker.txt"
    blocker.write_text("not a directory", encoding="utf-8")
    monkeypatch.setattr(cli, "select_plan", _fail_selector("dead runtime"))

    code = cli.main(
        ["--property", "trivial", "--decision-log", str(blocker / "sub" / "log.jsonl")]
    )
    captured = capsys.readouterr()

    assert code == cli.EXIT_SELECTOR_UNAVAILABLE
    assert json.loads(captured.out)["error"]["kind"] == "selector_unavailable"
    assert "decision log unavailable" in captured.err


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

    # Exit 2 stays reserved for rejected input, distinct from a dead runtime.
    assert proc.returncode == 2
    assert proc.stdout == ""
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
