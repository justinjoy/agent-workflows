from __future__ import annotations

import json
import re
import subprocess
import sys
import tarfile
import tomllib
import zipfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
EXPECTED_ATOMIC_SKILLS = {
    "classify-change-risk",
    "commit-atomic-change",
    "create-implementation-plan",
    "critique-plan",
    "implement-atomic-change",
    "inspect-repository",
    "report-result",
    "review-diff",
    "run-broad-tests",
    "run-focused-tests",
    "validate-final-design",
    "validate-final-risks",
}


def _json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def test_atomic_skills_exist_in_plugin_layout():
    skill_root = ROOT / "plugins" / "dev-workflows" / "skills"
    actual = {path.parent.name for path in skill_root.glob("*/SKILL.md")}

    assert EXPECTED_ATOMIC_SKILLS <= actual


def test_implementation_skill_resolves_installed_harness_forms():
    skill = (
        ROOT / "plugins" / "dev-workflows" / "skills" / "implementation-skill" / "SKILL.md"
    ).read_text(encoding="utf-8")

    assert "Wirelog-based implementation harness" in skill
    assert "evaluates Wirelog rules through PyreWire" in skill
    assert "<workspace>/.venv/bin/agent-workflows-harness" in skill
    assert "<workspace>/.venv/Scripts/agent-workflows-harness.exe" in skill
    assert "python -m agent_workflows_harness.cli" in skill
    assert "bare command is absent from `PATH`" in skill


def test_implementation_skill_requires_review_consensus_before_commit():
    skill_root = ROOT / "plugins" / "dev-workflows" / "skills"
    implementation = (skill_root / "implementation-skill" / "SKILL.md").read_text(
        encoding="utf-8"
    )
    commit = (skill_root / "commit-atomic-change" / "SKILL.md").read_text(
        encoding="utf-8"
    )

    assert (
        "Every code change, including documentation-only and trivial changes"
        in implementation
    )
    assert "Reviewer, Architect, and Critic approve the same candidate" in implementation
    assert "Stage only" in implementation
    assert "approved paths and hunks" in implementation
    assert "without `-a`, `--amend`, or `--no-verify`" in commit
    assert "Require a completely clean real index" in commit
    assert "without unstaging or repairing it" in commit
    assert "approved_candidate_tree" in commit
    assert "require `commit^{tree}` to equal" in commit
    assert "all three verified tree IDs" in commit

    gate_skills = (
        "run-focused-tests",
        "run-broad-tests",
        "review-diff",
        "validate-final-design",
        "validate-final-risks",
    )
    for skill_id in gate_skills:
        contract = (skill_root / skill_id / "SKILL.md").read_text(encoding="utf-8")
        assert "approved_candidate_tree" in contract

    review = (skill_root / "review-diff" / "SKILL.md").read_text(encoding="utf-8")
    assert "output must echo" in review
    assert "approved candidate path set" in review
    assert "content digest reviewed" in review


def test_provider_versions_follow_release_policy():
    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    expected_version = project["project"]["version"]

    coupled_plugin_manifests = [
        ROOT / "plugins" / "dev-workflows" / f".{host}-plugin" / "plugin.json"
        for host in ("antigravity", "gemini")
    ]
    coupled_marketplace_manifests = [
        ROOT / f".{host}-plugin" / "marketplace.json"
        for host in ("antigravity", "gemini")
    ]

    assert all(
        _json(path)["version"] == expected_version
        for path in coupled_plugin_manifests
    )
    assert all(
        _json(path)["plugins"][0]["version"] == expected_version
        for path in coupled_marketplace_manifests
    )

    claude_manifest = _json(
        ROOT / "plugins" / "dev-workflows" / ".claude-plugin" / "plugin.json"
    )
    claude_entry = _json(ROOT / ".claude-plugin" / "marketplace.json")["plugins"][0]
    assert claude_manifest["version"] == "1.1.1"
    assert "version" not in claude_entry

    codex_version = _json(
        ROOT / "plugins" / "dev-workflows" / ".codex-plugin" / "plugin.json"
    )["version"]
    cachebuster = re.fullmatch(
        rf"{re.escape(expected_version)}\+codex\.[A-Za-z0-9.-]+", codex_version
    )
    assert codex_version == expected_version or cachebuster is not None


def test_claude_marketplace_points_to_shared_lifecycle_skill_layout():
    marketplace = _json(ROOT / ".claude-plugin" / "marketplace.json")
    entry = marketplace["plugins"][0]
    plugin_root = (ROOT / entry["source"]).resolve()

    assert entry["source"] == "./plugins/dev-workflows"
    assert plugin_root.is_relative_to(ROOT.resolve())
    assert "strict" not in entry
    assert "version" not in entry
    assert {"review", "wirelog", "atomic-commit"} <= set(entry["tags"])

    manifest = _json(plugin_root / ".claude-plugin" / "plugin.json")
    implementation_path = plugin_root / "skills" / "implementation-skill" / "SKILL.md"
    commit_path = plugin_root / "skills" / "commit-atomic-change" / "SKILL.md"

    assert manifest["name"] == entry["name"] == "dev-workflows"
    assert manifest["version"] == "1.1.1"
    for description in (manifest["description"], entry["description"]):
        assert "mandatory review" in description
        assert "Architect/Critic approval" in description
        assert "verified atomic commits" in description
    assert implementation_path.is_file()
    assert commit_path.is_file()

    implementation = implementation_path.read_text(encoding="utf-8")
    commit = commit_path.read_text(encoding="utf-8")
    assert "including documentation-only and trivial changes" in implementation
    assert "commit-atomic-change" in implementation
    assert "Reviewer, Architect, and Critic approve" in implementation
    assert "approved_candidate_tree" in commit


def test_package_metadata_uses_wirelog_terminology():
    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    module_docstring = (
        ROOT / "src" / "agent_workflows_harness" / "__init__.py"
    ).read_text(encoding="utf-8")

    assert "Wirelog-based" in project["project"]["description"]
    assert "Wirelog-based" in module_docstring
    assert "Datalog" not in project["project"]["description"]
    assert "Datalog" not in module_docstring


def test_source_distribution_manifest_includes_plugin_assets():
    manifest = (ROOT / "MANIFEST.in").read_text(encoding="utf-8")

    assert "recursive-include plugins" in manifest
    assert "recursive-include docs" in manifest
    assert "include .agents/plugins/marketplace.json" in manifest
    assert "include .antigravity-plugin/marketplace.json" in manifest
    assert "include .claude-plugin/marketplace.json" in manifest
    assert "include .gemini-plugin/marketplace.json" in manifest


def test_built_artifacts_match_runtime_and_plugin_distribution_contract(tmp_path):
    subprocess.run(
        [
            sys.executable,
            "-m",
            "build",
            "--no-isolation",
            "--outdir",
            str(tmp_path),
            str(ROOT),
        ],
        check=True,
        text=True,
        capture_output=True,
    )

    sdist = next(tmp_path.glob("agent_workflows-*.tar.gz"))
    wheel = next(tmp_path.glob("agent_workflows-*.whl"))

    with tarfile.open(sdist, "r:gz") as archive:
        sdist_members = set(archive.getnames())
    required_suffixes = {
        ".agents/plugins/marketplace.json",
        ".antigravity-plugin/marketplace.json",
        ".claude-plugin/marketplace.json",
        ".gemini-plugin/marketplace.json",
        "plugins/dev-workflows/skills/report-result/SKILL.md",
        "plugins/dev-workflows/skills/commit-atomic-change/SKILL.md",
    }
    assert all(
        any(member.endswith(suffix) for member in sdist_members)
        for suffix in required_suffixes
    )

    with zipfile.ZipFile(wheel) as archive:
        wheel_members = set(archive.namelist())
    assert "agent_workflows_harness/cli.py" in wheel_members
    assert "agent_workflows_harness/selector.py" in wheel_members
    assert any(name.endswith(".dist-info/entry_points.txt") for name in wheel_members)
    assert not any(name.startswith("plugins/") for name in wheel_members)
