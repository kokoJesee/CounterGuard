"""Public inspection with real Git objects and explicit target mappings."""

import json
import os
import subprocess

import pytest
from typer.testing import CliRunner

from counterguard.change_analysis import inspect_repository, render_inspection
from counterguard.cli import app
from counterguard.digests import digest_json_artifact
from counterguard.repository import read_repository
from tests.repository_support import git, sample_repository
from tests.unit.test_project_config import project

pytestmark = pytest.mark.slow


def config_file(tmp_path, **updates):
    path = tmp_path / "config.json"
    path.write_text(json.dumps(project(**updates)), encoding="utf-8")
    return path


@pytest.mark.slow
def test_inspect_resolves_commits_and_maps_change_without_importing_target(tmp_path):
    repo = tmp_path / "repo"
    base, head = sample_repository(repo)
    config = tmp_path / "config.json"
    config.write_text(
        json.dumps(
            {
                "schema_version": "project-config.v1",
                "project_id": "fixture",
                "targets": [
                    {
                        "target_id": "pricing",
                        "guard_id": "grd_price",
                        "source_ref": "src/pricing.py",
                        "symbol": "price",
                        "contract_ref": "contracts/price.json",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    result = CliRunner().invoke(
        app,
        [
            "inspect",
            "--repo",
            str(repo),
            "--base",
            "HEAD~1",
            "--head",
            "HEAD",
            "--config",
            str(config),
            "--format",
            "json",
        ],
    )
    assert result.exit_code == 0, result.output
    report = json.loads(result.stdout)
    assert report["status"] == "ready"
    assert (report["base_commit"], report["head_commit"]) == (base, head)
    assert report["targets"][0]["impact"] == "affected"
    assert report["execution_allowed"] is False
    assert report["execution_outcome"] == "not_run"


@pytest.mark.parametrize("role", ["base", "head"])
def test_missing_revision_is_unknown_and_has_no_execution(tmp_path, role):
    repo = tmp_path / "repo"
    base, head = sample_repository(repo)
    values = {"base": base, "head": head, role: "does-not-exist"}
    result = inspect_repository(repo, values["base"], values["head"], config_file(tmp_path))
    assert result.status == "unknown"
    assert "missing_" + role + "_commit" in result.reason_codes
    assert result.targets[0].impact == "unknown" and result.execution_allowed is False


def test_dirty_worktree_and_invalid_repository_config_do_not_affect_committed_snapshot(tmp_path):
    repo = tmp_path / "repo"
    base, head = sample_repository(repo)
    config = config_file(tmp_path)
    first = inspect_repository(repo, base, head, config)
    (repo / "src/pricing.py").write_text("this is not Python", encoding="utf-8")
    (repo / ".git/config").write_text(
        "this is deliberately invalid Git configuration", encoding="utf-8"
    )
    second = inspect_repository(repo, base, head, config)
    assert second == first
    assert digest_json_artifact(first) == first.artifact_digest


def test_hooks_filters_original_git_config_and_git_environment_are_not_executed(
    tmp_path, monkeypatch
):
    repo = tmp_path / "repo"
    base, head = sample_repository(repo)
    marker = tmp_path / "should-not-exist"
    helper = tmp_path / "helper.sh"
    helper.write_text(f'#!/bin/sh\ntouch "{marker.as_posix()}"\nexit 99\n', encoding="utf-8")
    config = config_file(tmp_path)
    before = inspect_repository(repo, base, head, config)
    (repo / ".git/config").write_text(
        f'[core]\n fsmonitor = "{helper.as_posix()}"\n'
        f'[diff]\n external = "{helper.as_posix()}"\n'
        f'[filter "evil"]\n smudge = "{helper.as_posix()}"\n'
        "[include]\n path = /nonexistent/host-config\n",
        encoding="utf-8",
    )
    for name in ("post-checkout", "post-merge", "pre-command"):
        (repo / ".git/hooks" / name).write_bytes(helper.read_bytes())
    monkeypatch.setenv("GIT_DIR", str(tmp_path / "wrong"))
    monkeypatch.setenv("GIT_WORK_TREE", str(tmp_path / "wrong-tree"))
    monkeypatch.setenv("GIT_EXTERNAL_DIFF", str(helper))
    monkeypatch.setenv("GIT_CONFIG_COUNT", "1")
    monkeypatch.setenv("GIT_CONFIG_KEY_0", "core.fsmonitor")
    monkeypatch.setenv("GIT_CONFIG_VALUE_0", str(helper))
    assert inspect_repository(repo, base, head, config) == before
    assert not marker.exists()


def test_packed_refs_and_unrelated_refs_preserve_the_selected_commit_result(tmp_path):
    repo = tmp_path / "repo"
    base, head = sample_repository(repo)
    config = config_file(tmp_path)
    first = inspect_repository(repo, base, head, config)
    git(repo, "tag", "extra", base)
    git(repo, "pack-refs", "--all")
    assert inspect_repository(repo, base, head, config) == first


def test_real_shallow_clone_returns_unknown_without_fetching(tmp_path):
    source, clone = tmp_path / "source", tmp_path / "clone"
    sample_repository(source)
    git(tmp_path, "clone", "--depth", "1", "--no-local", str(source), str(clone))
    report = read_repository(clone, "HEAD~1", "HEAD")
    assert report.status == "unknown" and report.shallow
    assert report.reason_codes == ("shallow_history_insufficient",)


def test_external_object_store_is_rejected_before_git_starts(tmp_path, monkeypatch):
    repo = tmp_path / "repo"
    base, head = sample_repository(repo)
    (repo / ".git/objects/info/alternates").write_text("/outside/objects\n", encoding="utf-8")

    def forbidden(*args, **kwargs):
        pytest.fail("Alternates must be rejected without invoking Git")

    monkeypatch.setattr(subprocess, "Popen", forbidden)
    report = read_repository(repo, base, head)
    assert report.status == "rejected" and report.reason_codes == ("external_object_store",)


def test_gitfile_worktree_is_explicitly_unsupported_without_following_it(tmp_path, monkeypatch):
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / ".git").write_text("gitdir: /outside/private/metadata\n", encoding="utf-8")

    def forbidden(*args, **kwargs):
        pytest.fail("Unsupported layout must not launch Git")

    monkeypatch.setattr(subprocess, "Popen", forbidden)
    report = read_repository(repo, "HEAD~1", "HEAD")
    assert report.status == "unknown" and report.reason_codes == ("unsupported_git_layout",)


def test_junction_or_symlink_input_is_rejected_without_following(tmp_path):
    repo = tmp_path / "repo"
    base, head = sample_repository(repo)
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "private.py").write_text("private", encoding="utf-8")
    link = repo / "linked"
    if os.name == "nt":
        result = subprocess.run(
            ["cmd", "/c", "mklink", "/J", str(link), str(outside)], capture_output=True
        )
        assert result.returncode == 0, result.stderr
    else:
        link.symlink_to(outside, target_is_directory=True)
    report = read_repository(repo, base, head, ("linked/private.py",))
    assert report.status == "rejected"
    assert report.reason_codes == ("unsafe_repository_path_or_metadata",)
    assert (outside / "private.py").read_text() == "private"


def test_rename_is_reported_as_delete_add_without_guessing_symbol_movement(tmp_path):
    repo = tmp_path / "repo"
    _, base = sample_repository(repo)
    (repo / "src/pricing.py").rename(repo / "src/renamed.py")
    git(repo, "add", "-A")
    git(repo, "commit", "-m", "rename")
    report = read_repository(repo, base, "HEAD")
    assert report.status == "ready"
    assert [(r.path, r.kind) for r in report.changes] == [
        ("src/pricing.py", "D"),
        ("src/renamed.py", "A"),
    ]


def test_inspection_is_repeatable_read_only_and_renders_one_set_of_facts(tmp_path):
    repo = tmp_path / "repo"
    base, head = sample_repository(repo)
    config = config_file(tmp_path)
    before = {p: (p.read_bytes(), p.stat().st_mtime_ns) for p in repo.rglob("*") if p.is_file()}
    first = inspect_repository(repo, base, head, config)
    assert inspect_repository(repo, base, head, config) == first
    assert before == {
        p: (p.read_bytes(), p.stat().st_mtime_ns) for p in repo.rglob("*") if p.is_file()
    }
    assert json.loads(render_inspection(first, "json"))["artifact_digest"] == first.artifact_digest
    for format in ("text", "markdown"):
        text = render_inspection(first, format)
        assert "execution_allowed: false" in text and "affected" in text


def test_unmapped_change_has_cli_exit_four_and_preserves_reason_in_all_formats(tmp_path):
    repo = tmp_path / "repo"
    _, base = sample_repository(repo)
    (repo / "src/other.py").write_text("raise RuntimeError('do not execute')\n", encoding="utf-8")
    git(repo, "add", ".")
    git(repo, "commit", "-m", "unmapped")
    config = config_file(tmp_path)
    for format in ("json", "text", "markdown"):
        result = CliRunner().invoke(
            app,
            [
                "inspect",
                "--repo",
                str(repo),
                "--base",
                base,
                "--head",
                "HEAD",
                "--config",
                str(config),
                "--format",
                format,
            ],
        )
        assert result.exit_code == 4
        assert "unmapped_changed_paths" in result.stdout
        assert "unknown" in result.stdout


def test_gitlink_is_unknown_and_never_initializes_a_submodule(tmp_path):
    repo = tmp_path / "repo"
    _, base = sample_repository(repo)
    git(repo, "update-index", "--add", "--cacheinfo", f"160000,{base},vendor")
    git(repo, "commit", "-m", "gitlink")
    report = read_repository(repo, base, "HEAD")
    assert report.status == "unknown" and report.reason_codes == ("submodule_or_nonfile_entry",)
    assert not (repo / "vendor").exists()


def test_corrupt_object_is_rejected_instead_of_becoming_a_source_pin(tmp_path):
    repo = tmp_path / "repo"
    _, head = sample_repository(repo)
    oid = git(repo, "rev-parse", "HEAD:src/pricing.py")
    path = repo / ".git/objects" / oid[:2] / oid[2:]
    path.chmod(0o600)
    path.write_bytes(b"not a compressed git object")
    report = read_repository(repo, "HEAD~1", head)
    assert report.status == "rejected" and report.reason_codes == ("git_object_integrity",)


def test_committed_symbolic_entry_is_rejected_without_reading_its_destination(tmp_path):
    repo = tmp_path / "repo"
    _, base = sample_repository(repo)
    (repo / "link-payload").write_text("../../outside/private.py", encoding="utf-8")
    oid = git(repo, "hash-object", "-w", "link-payload")
    git(repo, "update-index", "--add", "--cacheinfo", f"120000,{oid},shortcut.py")
    git(repo, "commit", "-m", "symbolic tree entry")
    report = read_repository(repo, base, "HEAD")
    assert report.status == "rejected" and report.reason_codes == ("symbolic_tree_entry",)


def test_reference_change_during_inspection_returns_unknown(tmp_path, monkeypatch):
    repo = tmp_path / "repo"
    base, head = sample_repository(repo)
    original = subprocess.Popen

    def popen(argv, **kwargs):
        process = original(argv, **kwargs)
        if "diff-tree" in argv:
            (repo / ".git/HEAD").write_text(base + "\n", encoding="ascii")
        return process

    monkeypatch.setattr(subprocess, "Popen", popen)
    report = read_repository(repo, base, head)
    assert report.status == "unknown"
    assert report.reason_codes == ("repository_changed_during_inspection",)
