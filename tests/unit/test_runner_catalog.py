"""Discovery separates reviewed provenance from local availability and never runs images."""

import importlib
import json
from types import SimpleNamespace

import pytest
from typer.testing import CliRunner

from counterguard.cli import app
from counterguard.digests import canonical_json_bytes, digest_json_artifact
from counterguard.errors import ArtifactIntegrityError
from counterguard.runner_catalog import list_runners, load_catalog, resolve_runner

catalog_module = importlib.import_module("counterguard.runner_catalog")


def test_offline_discovery_has_sources_but_never_claims_available():
    report = list_runners(offline=True)
    assert len(report["runners"]) == 2
    assert report["image_execution_count"] == 0
    assert all(
        not row["usable"] and row["availability"] == "not_checked" for row in report["runners"]
    )
    for row in report["runners"]:
        assert row["provenance"]["attacks_passed"] == 4
        assert row["provenance"]["base_registry_digests"]


def test_discovery_preserves_unavailable_and_checks_exact_images(monkeypatch):
    seen = []

    def availability(image):
        seen.append(image)
        return "unavailable"

    monkeypatch.setattr(catalog_module, "_availability", availability)
    report = list_runners()
    assert report["exit_code"] == 3
    assert len(seen) == 2 and all(value.startswith("sha256:") for value in seen)
    assert not any(row["usable"] for row in report["runners"])


@pytest.mark.parametrize("identity,available", [("wrong", False), ("expected", True)])
def test_local_probe_only_inspects_identity(monkeypatch, identity, available):
    image = load_catalog().reviews[0].image_digest
    calls = []
    monkeypatch.setattr(catalog_module, "_docker_executable", lambda: "docker")

    def bounded(argv, **kwargs):
        calls.append(argv)
        return SimpleNamespace(
            returncode=0,
            timed_out=False,
            overflowed=False,
            stdout=(image if identity == "expected" else identity).encode(),
        )

    monkeypatch.setattr(catalog_module, "_run_bounded", bounded)
    assert (catalog_module._availability(image) == "available") is available
    assert calls[0][1:3] == ("image", "inspect")
    assert "run" not in calls[0]


def test_unknown_images_and_ambiguous_selection_are_rejected():
    with pytest.raises(ArtifactIntegrityError, match="no pinned review"):
        resolve_runner(runner_id=None, image_digest="sha256:" + "0" * 64)
    with pytest.raises(ValueError, match="exactly one"):
        resolve_runner(runner_id="root-pytest8", image_digest="sha256:" + "0" * 64)
    root = resolve_runner(runner_id="root-pytest8", image_digest=None)
    assert resolve_runner(runner_id=None, image_digest=root.image_digest) == root


def test_rehashing_a_modified_catalog_does_not_create_an_approval(tmp_path, monkeypatch):
    data = json.loads(catalog_module.CATALOG_PATH.read_bytes())
    data["reviews"][0]["image_digest"] = "sha256:" + "0" * 64
    data["reviews"][0]["artifact_digest"] = digest_json_artifact(data["reviews"][0])
    data["artifact_digest"] = digest_json_artifact(data)
    path = tmp_path / "catalog.json"
    path.write_bytes(canonical_json_bytes(data))
    monkeypatch.setattr(catalog_module, "CATALOG_PATH", path)
    with pytest.raises(ArtifactIntegrityError, match="invalid"):
        load_catalog()


def test_cli_offline_lists_reviewed_names_and_sources_without_processes():
    result = CliRunner().invoke(app, ["runner", "list", "--offline", "--format", "json"])
    assert result.exit_code == 0, result.output
    assert json.loads(result.output)["runners"][0]["provenance"]["attack_receipt_digest"]
    result = CliRunner().invoke(app, ["runner", "show", "validators-pytest9", "--offline"])
    assert result.exit_code == 0 and "9.0.3" in result.output


@pytest.mark.parametrize("change", ["missing", "tamper", "rehash", "oversize"])
@pytest.mark.parametrize(
    "filename",
    ["root-build.json", "root-attacks.json", "validators-build.json", "validators-attacks.json"],
)
def test_receipt_damage_fails_before_any_local_probe(tmp_path, monkeypatch, change, filename):
    import shutil

    shutil.copytree(catalog_module.RECEIPTS_PATH, tmp_path / "receipts")
    monkeypatch.setattr(catalog_module, "RECEIPTS_PATH", tmp_path / "receipts")
    monkeypatch.setattr(catalog_module, "_availability", lambda *_: pytest.fail("Docker probed"))
    path = tmp_path / "receipts" / filename
    if change == "missing":
        path.unlink()
    elif change == "oversize":
        path.write_bytes(b" " * 131073)
    else:
        data = json.loads(path.read_bytes())
        data["image_id"] = "sha256:" + "f" * 64
        if change == "rehash":
            data["artifact_digest"] = digest_json_artifact(data)
        path.write_bytes(canonical_json_bytes(data))
    with pytest.raises(ArtifactIntegrityError):
        list_runners()
    with pytest.raises(ArtifactIntegrityError):
        resolve_runner(runner_id="root-pytest8", image_digest=None)
    result = CliRunner().invoke(app, ["runner", "list", "--offline"])
    assert result.exit_code == 5 and "available" not in result.output


def test_available_requires_all_receipts_and_exact_image(monkeypatch):
    monkeypatch.setattr(catalog_module, "_availability", lambda *_: "available")
    report = list_runners()
    assert report["schema_version"] == "runner-discovery.v2"
    assert all(
        row["usable"] and row["receipt_integrity"] == "verified" for row in report["runners"]
    )


def test_bundled_receipts_preserve_the_public_source_bytes():
    from pathlib import Path

    root = Path(__file__).resolve().parents[2]
    for review in load_catalog().reviews:
        for ref in (review.build_receipt_ref, review.attack_receipt_ref):
            assert (root / ref).read_bytes() == (
                catalog_module.RECEIPTS_PATH / Path(ref).name
            ).read_bytes()
