"""Data consistency cannot become human semantics, a label or execution authority."""

import copy
import importlib
import json
import random
import subprocess
from pathlib import Path

import pytest

from counterguard.digests import canonical_json_bytes, digest_json_artifact
from scripts.audit_rgb_mapping import MappingAuditError, audit_mapping, main

ROOT = Path(__file__).resolve().parents[2]
CONTRACT = ROOT / "docs/results/static-reexport-v1/termcolor-contract.json"
WORKSHEET = ROOT / "docs/results/bounded-rgb-targets-v1/colored-cprint-proposal.json"
INSPECTION = ROOT / "docs/results/static-reexport-v2/colored-target.json"


def inputs():
    return (
        CONTRACT.read_bytes(),
        json.loads(WORKSHEET.read_bytes()),
        json.loads(INSPECTION.read_bytes()),
    )


def sealed(value):
    value = copy.deepcopy(value)
    value["artifact_digest"] = digest_json_artifact(value)
    return canonical_json_bytes(value)


def test_all_cases_and_full_oracles_preserved_without_process_or_target_import(monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("read-only mapping audit launched a process")

    monkeypatch.setattr(subprocess, "Popen", forbidden)
    original = importlib.import_module

    def guarded(name, *args, **kwargs):
        assert name.split(".")[0] not in {"colored", "termcolor"}
        return original(name, *args, **kwargs)

    monkeypatch.setattr(importlib, "import_module", guarded)
    raw, worksheet, inspection = inputs()
    value = audit_mapping(raw, sealed(worksheet), sealed(inspection))
    assert value["source_case_count"] == value["mapped_case_count"] == 8
    assert value["input_shape_counts"] == {
        "malformed_integer_tuple_length": 4,
        "three_integer_channels_out_of_range": 4,
    }
    assert value["target_execution_count"] == 0 and value["execution_allowed"] is False
    assert not value["mapping_semantics_approved"] and not value["labels_assigned"]
    assert not value["source_evidence_guard_currently_verified"]
    for row in value["rows"]:
        assert row["preserved_oracle"] == {
            "oracle": "raises",
            "exception": "ValueError",
            "exception_match": "Expected a tuple of 3 ints in range 0-255",
        }
        assert len(row["target_keyword_args"]) == 1
        assert row["target_keyword_args"][0]["name"] in {"fore_rgb", "back_rgb"}
        assert row["source_only_control"]["name"] == "force_color"


@pytest.mark.parametrize(
    "attack,reason",
    [
        ("drop", "source_cases_missing_duplicated_or_added"),
        ("duplicate", "source_cases_missing_duplicated_or_added"),
        ("invent", "source_cases_missing_duplicated_or_added"),
        ("count", "worksheet_count_mismatch"),
        ("role", "foreground_background_role_changed"),
        ("literal", "rgb_literal_changed"),
        ("bool", "rgb_literal_changed"),
        ("float", "rgb_literal_changed"),
        ("text", "positional_literal_changed"),
        ("unpack", "mapping_must_not_unpack_run_or_label"),
        ("label", "mapping_must_not_unpack_run_or_label"),
        ("match", "source_oracle_changed_or_unsupported"),
        ("exception", "source_oracle_changed_or_unsupported"),
        ("assertion", "source_assertion_identity_mismatch"),
        ("control", "source_control_must_not_be_forwarded"),
        ("extra", "mapping_row_fields_unsupported"),
        ("approved", "worksheet_must_remain_unapproved_and_unexecuted"),
    ],
)
def test_resigning_cannot_drop_inputs_change_oracles_or_self_approve(attack, reason):
    raw, worksheet, inspection = inputs()
    row = worksheet["mapping_worksheet"][0]
    if attack == "drop":
        worksheet["mapping_worksheet"].pop()
    elif attack == "duplicate":
        worksheet["mapping_worksheet"][-1] = copy.deepcopy(row)
    elif attack == "invent":
        row["source_case_id"] = "case_invented"
    elif attack == "count":
        worksheet["source_case_count"] = 80
    elif attack == "role":
        row["proposed_target_rgb_keyword"] = "back_rgb"
    elif attack in {"literal", "bool", "float"}:
        row["proposed_target_rgb_literal"]["items"][1]["value"] = {
            "literal": 255,
            "bool": False,
            "float": 0.0,
        }[attack]
    elif attack == "text":
        row["proposed_target_positional_args"][0]["value"] = "changed"
    elif attack == "unpack":
        row["adapter_tuple_unpacking"] = True
    elif attack == "label":
        row["label"] = "inapplicable"
    elif attack == "match":
        row["preserved_exception_match"] = ""
    elif attack == "exception":
        row["source_exception"] = "TypeError"
    elif attack == "assertion":
        row["source_assertion_digest"] = "sha256:" + "0" * 64
    elif attack == "control":
        row["source_force_color_handling"] = "forward_to_print"
    elif attack == "extra":
        row["review_override"] = True
    else:
        worksheet["mapping_semantics_approved"] = True
    with pytest.raises(MappingAuditError, match=reason):
        audit_mapping(raw, sealed(worksheet), sealed(inspection))


@pytest.mark.parametrize(
    "attack,reason",
    [
        ("target", "target_identity_mismatch"),
        ("revision", "target_identity_mismatch"),
        ("unknown", "target_inputs_unresolved"),
        ("finding", "target_inputs_unresolved"),
        ("pin", "closure_not_bound_to_committed_tree"),
        ("duplicate", "duplicate_or_empty_target_pins"),
        ("export", "export_identity_mismatch"),
        ("execute", "inspection_is_not_a_read_only_receipt"),
        ("schema", "unsupported_input_schema"),
    ],
)
def test_target_receipt_mismatches_do_not_become_admission(attack, reason):
    raw, worksheet, inspection = inputs()
    if attack == "target":
        inspection["target"] = "colored:fore_rgb"
    elif attack == "revision":
        inspection["commit"] = "0" * 40
    elif attack == "unknown":
        inspection["runtime_assessment"]["status"] = "unknown"
    elif attack == "finding":
        inspection["runtime_assessment"]["findings"] = [{"code": "unresolved"}]
    elif attack == "pin":
        inspection["runtime_assessment"]["files"][0]["content_digest"] = "sha256:" + "0" * 64
    elif attack == "duplicate":
        inspection["files"].append(inspection["files"][0])
    elif attack == "export":
        inspection["runtime_assessment"]["static_export"]["target_symbol"] = "other"
    elif attack == "execute":
        inspection["execution_allowed"] = True
    else:
        inspection["schema_version"] = "static-target-inspection.v99"
    with pytest.raises(MappingAuditError, match=reason):
        audit_mapping(raw, sealed(worksheet), sealed(inspection))


def test_twenty_row_shuffles_keep_semantics_and_record_actual_input_byte_changes():
    raw, worksheet, inspection = inputs()
    expected = audit_mapping(raw, sealed(worksheet), sealed(inspection))
    assert expected == audit_mapping(raw, sealed(worksheet), sealed(inspection))
    saw_different_bytes = False
    for seed in range(20):
        random.Random(seed).shuffle(worksheet["mapping_worksheet"])
        actual = audit_mapping(raw, sealed(worksheet), sealed(inspection))
        assert actual["rows"] == expected["rows"]
        assert actual["semantic_digest"] == expected["semantic_digest"]
        if actual["input_byte_digests"] != expected["input_byte_digests"]:
            saw_different_bytes = True
            assert actual["artifact_digest"] != expected["artifact_digest"]
    assert saw_different_bytes


def test_cli_writes_new_read_only_audit_and_refuses_overwrite_or_approval(
    tmp_path, monkeypatch, capsys
):
    monkeypatch.chdir(tmp_path)
    command = [
        "--source-contract",
        str(CONTRACT),
        "--worksheet",
        str(WORKSHEET),
        "--target-inspection",
        str(INSPECTION),
        "--output",
        "new-audit",
    ]
    assert main(command) == 4
    assert (tmp_path / "new-audit/mapping-audit.json").is_file()
    capsys.readouterr()
    assert main(command) == 5
    assert "output_exists_choose_new_id" in capsys.readouterr().out
    with pytest.raises(SystemExit) as error:
        main([*command, "--approve"])
    assert error.value.code == 2


def test_ambiguous_input_or_missing_source_is_a_sanitized_refusal(tmp_path, monkeypatch, capsys):
    with pytest.raises(ValueError):
        audit_mapping(CONTRACT.read_bytes(), b'{"x":1,"x":2}', INSPECTION.read_bytes())
    monkeypatch.chdir(tmp_path)
    assert (
        main(
            [
                "--source-contract",
                str(tmp_path / "private-name"),
                "--worksheet",
                str(WORKSHEET),
                "--target-inspection",
                str(INSPECTION),
                "--output",
                "bad-audit",
            ]
        )
        == 5
    )
    assert json.loads(capsys.readouterr().out) == {
        "status": "rejected",
        "reason_code": "input_missing_linked_or_oversized",
    }
