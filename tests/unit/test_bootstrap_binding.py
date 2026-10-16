"""Re-signing provenance cannot substitute for reconstructing committed B/F/H."""

import copy
import hashlib
import importlib
import json
import random
from pathlib import Path

import pytest
from pydantic import ValidationError
from typer.testing import CliRunner

from counterguard.bootstrap_binding import bind_contract, prepare_contract, verify_binding
from counterguard.cli import app
from counterguard.digests import canonical_json_bytes, digest_bytes, digest_json_artifact
from counterguard.errors import ArtifactIntegrityError
from counterguard.models import Guard
from counterguard.repository import FilePin, RepositoryProblem
from counterguard.repository_models import RepositoryGuard
from counterguard.standalone_contracts import read_standalone_contract, strict_json

binding = importlib.import_module("counterguard.bootstrap_binding")
B, F, H = "a" * 40, "b" * 40, "c" * 40
REF = "contracts/price.v1.json"


def pins(files):
    return tuple(
        FilePin(
            revision="head",
            path=ref,
            object_id=hashlib.sha1(
                b"blob " + str(len(raw)).encode() + b"\0" + raw, usedforsecurity=False
            ).hexdigest(),
            content_digest=digest_bytes(raw),
        )
        for ref, raw in files.items()
    )


@pytest.fixture
def repository(tmp_path, monkeypatch):
    repo = tmp_path / "repo"
    repo.mkdir()
    buggy = {
        "sample/__init__.py": b"raise RuntimeError('never execute target')\n",
        "sample/core.py": b"def price(x): return x\n",
        "pyproject.toml": b'[project]\nname="sample"\ndependencies=[]\n',
        "tests/conftest.py": b"raise RuntimeError('never load project bootstrap')\n",
    }
    fixed = {
        **buggy,
        "sample/core.py": b"def price(x): return x + 1\n",
        "tests/test_price.py": b"from sample.core import price\n"
        b"def test_price():\n assert price(1) == 2\n assert price(price(1)) == 3\n",
    }
    trees = {B: buggy, F: fixed}
    metadata = {B: (), F: (B,), H: (F,)}

    def committed(_, revision):
        if revision not in trees:
            raise RepositoryProblem("missing_object")
        return revision, trees[revision], pins(trees[revision])

    monkeypatch.setattr(binding, "read_committed_files", committed)
    monkeypatch.setattr(
        binding,
        "read_commit_metadata",
        lambda _, revision: {
            "commit": revision,
            "parents": metadata[revision],
            "message": "fixture",
        },
    )
    monkeypatch.chdir(tmp_path)
    prepare_contract(
        repo,
        buggy=B,
        fixed=F,
        contract_id="price.v1",
        target="sample.core:price",
        import_root=".",
        test_ref="tests/test_price.py",
        test_function="test_price",
        output=Path("prepared"),
    )
    raw = Path("prepared/contract.json").read_bytes()
    trees[H] = {**fixed, REF: raw}
    return repo, trees, metadata


def bind(repo, name="bound"):
    return bind_contract(repo, H, REF, output=Path(name))


def test_preparation_roundtrip_and_head_binding_do_not_claim_runtime_truth(repository):
    repo, _, _ = repository
    preparation = json.loads(Path("prepared/preparation.json").read_bytes())
    assert preparation["human_review_required"] and not preparation["execution_allowed"]
    contract = read_standalone_contract(Path("prepared/contract.json").read_bytes())
    assert contract.schema_version == "contract.v3" and len(contract.cases) == 1
    value = bind(repo)
    assert value["binding_status"] == "sources_verified"
    assert value["capture_input_status"] == "review_required"
    assert value["reproduced"] is None and not value["execution_allowed"]
    assert not value["capture_available"] and value["execution_outcome"] == "not_run"
    assert value["projection_coverage"]["source_assertions"] == 2
    assert value["projection_coverage"]["represented_assertions"] == 1
    assert value["projection_coverage"]["unsupported"][0]["assertion_count"] == 1
    assert value["file_origins"][REF]["commit"] == H
    assert value["ownership_authentication"] == "not_provided_by_git_object_integrity"
    assert verify_binding(repo, Path("bound/binding.json")) == value
    for model in (Guard, RepositoryGuard):
        with pytest.raises(ValidationError):
            model.model_validate(value)
    with pytest.raises(ArtifactIntegrityError):
        bind(repo)


@pytest.mark.parametrize(
    "attack,reason",
    [
        ("missing_contract", "contract_missing_from_head"),
        ("modified_head_source", "owner_head_must_only_add_contract"),
        ("modified_head_test", "owner_head_must_only_add_contract"),
        ("extra_owner_file", "owner_head_must_only_add_contract"),
        ("head_not_fixed_child", "head_must_be_contract_child_of_fixed"),
        ("merge_fix", "fix_must_have_one_buggy_parent"),
        ("missing_buggy", "missing_object"),
        ("oracle", "contract_cases_differ_from_fixed_test"),
        ("origin", "test_origin_or_projection_mismatch"),
        ("omit_initializer", "runtime_closure_union_mismatch"),
        ("extra_runtime_ref", "runtime_closure_union_mismatch"),
        ("unchanged_runtime", "runtime_sources_did_not_change"),
    ],
)
def test_rejects_damaged_or_redeclared_chain_and_preserves_failure(repository, attack, reason):
    repo, trees, metadata = repository
    data = json.loads(trees[H][REF])
    if attack == "missing_contract":
        del trees[H][REF]
    elif attack == "modified_head_source":
        trees[H]["sample/core.py"] = b"def price(x): return 0\n"
    elif attack == "modified_head_test":
        trees[H]["tests/test_price.py"] += b"# changed\n"
    elif attack == "extra_owner_file":
        trees[H]["counterguard.yaml"] = b"{}"
    elif attack == "head_not_fixed_child":
        metadata[H] = (B,)
    elif attack == "merge_fix":
        metadata[F] = (B, "d" * 40)
    elif attack == "missing_buggy":
        del trees[B]
    elif attack == "oracle":
        data["cases"][0]["expected"]["value"] = 100
    elif attack == "origin":
        data["test_origin"]["projection_digest"] = "sha256:" + "0" * 64
    elif attack == "omit_initializer":
        data["runtime_refs"].remove("sample/__init__.py")
    elif attack == "extra_runtime_ref":
        data["runtime_refs"].append("unused.py")
    elif attack == "unchanged_runtime":
        trees[B]["sample/core.py"] = trees[F]["sample/core.py"]
    if attack in {"oracle", "origin", "omit_initializer", "extra_runtime_ref"}:
        trees[H][REF] = canonical_json_bytes(data)
    value = bind(repo)
    assert value["reason_code"] == reason
    assert not value["execution_allowed"] and Path("bound/binding-failure.json").is_file()
    assert not Path("bound/binding.json").exists()


@pytest.mark.parametrize(
    "field,value",
    [
        ("execution_allowed", True),
        ("reproduced", True),
        ("capture_available", True),
        ("capture_input_status", "approved"),
        ("binding_status", "approved"),
    ],
)
def test_re_signed_binding_cannot_forge_conclusions(repository, field, value):
    repo, _, _ = repository
    fact = bind(repo)
    fact[field] = value
    fact["artifact_digest"] = digest_json_artifact(fact)
    Path("forged.json").write_bytes(canonical_json_bytes(fact))
    with pytest.raises(ArtifactIntegrityError, match="does_not_match"):
        verify_binding(repo, Path("forged.json"))


def test_current_implementation_is_required_and_tampered_file_pins_are_rebuilt(repository):
    repo, _, _ = repository
    fact = bind(repo)
    fact["implementation_digests"] = {}
    fact["artifact_digest"] = digest_json_artifact(fact)
    Path("stale.json").write_bytes(canonical_json_bytes(fact))
    with pytest.raises(ArtifactIntegrityError, match="implementation_is_stale"):
        verify_binding(repo, Path("stale.json"))
    fact = json.loads(Path("bound/binding.json").read_bytes())
    fact["trees"]["buggy"]["files"][0]["content_digest"] = "sha256:" + "0" * 64
    fact["artifact_digest"] = digest_json_artifact(fact)
    Path("forged-pins.json").write_bytes(canonical_json_bytes(fact))
    with pytest.raises(ArtifactIntegrityError, match="does_not_match"):
        verify_binding(repo, Path("forged-pins.json"))


def test_twenty_shuffles_preserve_full_binding_and_digest(repository):
    repo, trees, _ = repository
    expected = bind(repo)
    for seed in range(20):
        for revision, files in list(trees.items()):
            items = list(files.items())
            random.Random(seed).shuffle(items)
            trees[revision] = dict(items)
        assert bind(repo, f"shuffle-{seed}") == expected


def test_prepare_uses_union_of_role_specific_runtime_closures(repository):
    repo, trees, _ = repository
    trees[B]["sample/old.py"] = b"value=0\n"
    trees[B]["sample/core.py"] = b"from .old import value\ndef price(x): return x+value\n"
    prepare_contract(
        repo,
        buggy=B,
        fixed=F,
        contract_id="price.v2",
        target="sample.core:price",
        import_root=".",
        test_ref="tests/test_price.py",
        test_function="test_price",
        output=Path("prepared-union"),
    )
    trees[H][REF] = Path("prepared-union/contract.json").read_bytes()
    value = bind(repo)
    assert value["binding_status"] == "sources_verified"
    assert "sample/old.py" in value["contract"]["runtime_refs"]
    assert "sample/old.py" not in {
        item["path"] for item in value["runtime_assessments"]["fixed"]["files"]
    }


@pytest.mark.parametrize(
    "source,expected",
    [
        (b"import external_package\ndef price(x): return x+1\n", "unknown"),
        (b"getattr(object(), 'x')\ndef price(x): return x+1\n", "unknown"),
        (b"@decorator\ndef price(x): return x+1\n", "unknown"),
    ],
)
def test_uncertainty_is_not_promoted_to_capture_permission(repository, source, expected):
    repo, trees, _ = repository
    trees[F]["sample/core.py"] = trees[H]["sample/core.py"] = source
    # Same file set and literal projection; additional imports/findings remain
    # unresolved in the source assessment, regardless of valid source hashes.
    value = bind(repo)
    assert value["binding_status"] == "sources_verified"
    assert value["capture_input_status"] == expected and not value["execution_allowed"]


def test_cli_binding_and_independent_verification_are_source_only(repository):
    repo, _, _ = repository
    result = CliRunner().invoke(
        app,
        [
            "bootstrap",
            "bind",
            "--repo",
            str(repo),
            "--head",
            H,
            "--contract-ref",
            REF,
            "--output",
            "cli",
        ],
    )
    assert result.exit_code == 0, result.output
    assert not json.loads(result.stdout)["execution_allowed"]
    result = CliRunner().invoke(
        app, ["bootstrap", "verify-binding", "cli/binding.json", "--repo", str(repo)]
    )
    assert result.exit_code == 0 and json.loads(result.stdout)["source_binding_verified"]
    missing = CliRunner().invoke(
        app,
        [
            "bootstrap",
            "bind",
            "--repo",
            str(repo),
            "--head",
            F,
            "--contract-ref",
            REF,
            "--output",
            "missing",
        ],
    )
    assert missing.exit_code == 5
    assert json.loads(missing.stdout)["reason_code"] == "contract_missing_from_head"


@pytest.mark.parametrize(
    "raw", [b'{"x":1,"x":2}', b'{"x":{"a":1,"a":2}}', b'{"x":NaN}', b'{"x":Infinity}', b"[]"]
)
def test_json_ambiguities_are_rejected(raw):
    with pytest.raises(ValueError):
        strict_json(raw, limit=1024)


def test_new_contract_model_keeps_existing_oracle_and_path_limits(repository):
    repo, trees, _ = repository
    original = json.loads(trees[H][REF])
    mutations = []
    changed = copy.deepcopy(original)
    changed["schema_version"] = "contract.v2"
    mutations.append(changed)
    changed = copy.deepcopy(original)
    changed["execution_allowed"] = True
    mutations.append(changed)
    changed = copy.deepcopy(original)
    changed["source_ref"] = "../core.py"
    mutations.append(changed)
    changed = copy.deepcopy(original)
    changed["cases"][0]["oracle"] = "eval"
    mutations.append(changed)
    changed = copy.deepcopy(original)
    changed["cases"][0]["expected"] = None
    mutations.append(changed)
    for changed in mutations:
        with pytest.raises(ValidationError):
            read_standalone_contract(canonical_json_bytes(changed))
    with pytest.raises(ValueError, match="budget"):
        strict_json(b"{}", limit=1)
    with pytest.raises(ValueError, match="outside target"):
        bind_contract(repo, H, REF, output=repo / "result")


def test_contract_argument_and_literal_depth_budgets(repository):
    _, trees, _ = repository
    value = json.loads(trees[H][REF])
    value["cases"][0]["positional_args"] *= 33
    with pytest.raises(ValidationError, match="argument budget"):
        read_standalone_contract(canonical_json_bytes(value))
    value = json.loads(trees[H][REF])
    literal = {"kind": "none"}
    for _ in range(10):
        literal = {"kind": "list", "items": [literal]}
    value["cases"][0]["expected"] = literal
    with pytest.raises(ValidationError, match="literal budget"):
        read_standalone_contract(canonical_json_bytes(value))


def test_preparation_never_publishes_a_contract_its_reader_cannot_accept(repository, monkeypatch):
    repo, _, _ = repository
    monkeypatch.setattr(binding, "CONTRACT_LIMIT", 1)
    with pytest.raises(ArtifactIntegrityError, match="prepared_contract_byte_budget"):
        prepare_contract(
            repo,
            buggy=B,
            fixed=F,
            contract_id="price.v2",
            target="sample.core:price",
            import_root=".",
            test_ref="tests/test_price.py",
            test_function="test_price",
            output=Path("too-big"),
        )
    assert not Path("too-big").exists()


def test_oversized_binding_is_a_retained_refusal_not_an_unverifiable_success(
    repository, monkeypatch
):
    repo, _, _ = repository
    monkeypatch.setattr(binding, "BINDING_LIMIT", 100)
    value = bind(repo)
    assert value["reason_code"] == "binding_byte_budget_exceeded"
    assert Path("bound/binding-failure.json").is_file()
    assert not Path("bound/binding.json").exists()


@pytest.mark.parametrize(
    "metadata,status",
    [
        (b'[project]\nname="sample"\n', "review_required"),
        (b'[project]\nname="sample"\ndependencies=["external"]\n', "blocked"),
        (b'[project]\nname="sample"\ndynamic=["dependencies"]\n', "unknown"),
    ],
)
def test_source_only_profile_does_not_hide_dependency_installation(repository, metadata, status):
    repo, trees, _ = repository
    for files in trees.values():
        files["pyproject.toml"] = metadata
    value = bind(repo)
    assert value["binding_status"] == "sources_verified"
    assert value["capture_input_status"] == status and not value["execution_allowed"]
