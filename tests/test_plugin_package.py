from __future__ import annotations

import json
import subprocess
import sys
import tarfile
import tomllib
import zipfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
EXPECTED_ATOMIC_SKILLS = {
    "classify-change-risk",
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


def test_plugin_and_marketplace_versions_match_python_package():
    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    expected_version = project["project"]["version"]

    plugin_manifests = [
        ROOT / "plugins" / "dev-workflows" / f".{host}-plugin" / "plugin.json"
        for host in ("antigravity", "claude", "codex", "gemini")
    ]
    marketplace_manifests = [
        ROOT / f".{host}-plugin" / "marketplace.json"
        for host in ("antigravity", "claude", "gemini")
    ]

    assert all(_json(path)["version"] == expected_version for path in plugin_manifests)
    assert all(
        _json(path)["plugins"][0]["version"] == expected_version
        for path in marketplace_manifests
    )


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
