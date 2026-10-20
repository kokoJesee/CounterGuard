"""Read-only literal mapping checks; not target semantics, provenance or authorization."""

import argparse
import json
from pathlib import Path

from counterguard.artifacts import write_immutable
from counterguard.digests import canonical_json_bytes, digest_bytes, digest_json_artifact
from counterguard.errors import ArtifactIntegrityError
from counterguard.project_config import reject_links
from counterguard.standalone_contracts import read_standalone_contract, strict_json

ALGORITHM = "rgb-literal-map-audit.v1"
LIMIT = 4 * 1024 * 1024
ROLES = {"color": "fore_rgb", "on_color": "back_rgb"}
CONTROL_HANDLING = "source_only_colorization_control_not_a_colored_parameter"
ROW_FIELDS = frozenset(
    {
        "adapter_tuple_unpacking",
        "execution_outcome",
        "label",
        "preserved_exception_match",
        "proposed_target_positional_args",
        "proposed_target_rgb_keyword",
        "proposed_target_rgb_literal",
        "source_assertion_digest",
        "source_case_id",
        "source_exception",
        "source_force_color_handling",
        "source_positional_args",
        "source_rgb_keyword",
        "source_rgb_literal",
    }
)


class MappingAuditError(ValueError):
    """Finite refusal code, with no target text or local path."""


def require(condition, code):
    if not condition:
        raise MappingAuditError(code)


def identical(left, right):
    # Python equality conflates True/1/1.0; literal transport must not do so.
    return canonical_json_bytes(left) == canonical_json_bytes(right)


def artifact(raw, schema):
    value = strict_json(raw, limit=LIMIT)
    require(value.get("schema_version") == schema, "unsupported_input_schema")
    require(value.get("artifact_digest") == digest_json_artifact(value), "input_digest_mismatch")
    return value


def _target(inspection, worksheet):
    require(
        inspection.get("execution_allowed") is False
        and inspection.get("execution_outcome") == "not_run"
        and inspection.get("cross_repository_execution_supported") is False,
        "inspection_is_not_a_read_only_receipt",
    )
    require(
        inspection.get("target") == worksheet.get("public_target")
        and inspection.get("commit") == worksheet.get("revision")
        and inspection.get("profile") == "standalone-static-reexport.v2",
        "target_identity_mismatch",
    )
    closure = inspection.get("runtime_assessment", {})
    require(isinstance(closure, dict), "target_inputs_unresolved")
    require(
        closure.get("status") == "review_required"
        and closure.get("algorithm") == "module-import-closure.v2"
        and closure.get("findings") == []
        and closure.get("static_export", {}).get("algorithm") == "static-root-reexport.v2",
        "target_inputs_unresolved",
    )
    all_pins = inspection.get("files", [])
    require(
        isinstance(all_pins, list)
        and all(
            isinstance(p, dict)
            and isinstance(p.get("path"), str)
            and isinstance(p.get("content_digest"), str)
            for p in all_pins
        ),
        "invalid_target_pins",
    )
    refs = [item["path"] for item in all_pins]
    require(len(refs) == len(set(refs)) and bool(refs), "duplicate_or_empty_target_pins")
    full = {item["path"]: item["content_digest"] for item in all_pins}
    selected = closure.get("files", [])
    require(
        isinstance(selected, list)
        and all(
            isinstance(p, dict)
            and isinstance(p.get("path"), str)
            and isinstance(p.get("content_digest"), str)
            for p in selected
        ),
        "invalid_closure_pins",
    )
    names = [item["path"] for item in selected]
    require(names == sorted(set(names)) and bool(names), "invalid_closure_pins")
    require(
        all(full.get(item["path"]) == item["content_digest"] for item in selected),
        "closure_not_bound_to_committed_tree",
    )
    public_module, public_symbol = inspection["target"].split(":")
    export = closure["static_export"]
    require(isinstance(export, dict), "export_identity_mismatch")
    require(
        export.get("target_module") == public_module
        and export.get("target_symbol") == public_symbol,
        "export_identity_mismatch",
    )
    for pin in export.get("files", []):
        require(
            pin["path"] in names and full.get(pin["path"]) == pin["content_digest"],
            "export_not_bound_to_closure",
        )
    return {
        "commit": inspection["commit"],
        "target": inspection["target"],
        "import_root": inspection["import_root"],
        "closure_pins": selected,
    }


def audit_mapping(contract_raw: bytes, worksheet_raw: bytes, inspection_raw: bytes) -> dict:
    """Check every source payload/oracle once; never evaluate or generate target code."""
    contract = read_standalone_contract(contract_raw)
    worksheet = artifact(worksheet_raw, "colored-cprint-followup-proposal.v1")
    inspection = artifact(inspection_raw, "static-target-inspection.v1")
    require(
        worksheet.get("source_contract_digest") == digest_bytes(contract_raw),
        "source_contract_digest_mismatch",
    )
    require(
        worksheet.get("execution_allowed") is False
        and worksheet.get("labels_assigned") is False
        and worksheet.get("mapping_semantics_approved") is False
        and worksheet.get("mapping_is_an_executable_contract") is False
        and type(worksheet.get("external_target_execution_count")) is int
        and worksheet["external_target_execution_count"] == 0,
        "worksheet_must_remain_unapproved_and_unexecuted",
    )
    target = _target(inspection, worksheet)
    mappings = worksheet.get("mapping_worksheet", [])
    require(
        isinstance(mappings, list) and all(isinstance(row, dict) for row in mappings),
        "mapping_rows_required",
    )
    cases = {case.case_id: case for case in contract.cases}
    require(
        all(
            type(worksheet.get(field)) is int and worksheet[field] == len(cases)
            for field in ("source_case_count", "proposed_literal_payload_mapping_count")
        ),
        "worksheet_count_mismatch",
    )
    ids = [row.get("source_case_id") for row in mappings]
    require(
        len(ids) == len(cases) and len(set(ids)) == len(ids) and set(ids) == set(cases),
        "source_cases_missing_duplicated_or_added",
    )
    rows = []
    for mapping in mappings:
        require(set(mapping) == ROW_FIELDS, "mapping_row_fields_unsupported")
        require(
            mapping["adapter_tuple_unpacking"] is False
            and mapping["execution_outcome"] == "not_run"
            and mapping["label"] == "unassigned",
            "mapping_must_not_unpack_run_or_label",
        )
        case = cases[mapping["source_case_id"]]
        data = case.model_dump(mode="json")
        keywords = {item["name"]: item["literal"] for item in data["keyword_args"]}
        rgb_keys = set(keywords) & set(ROLES)
        require(
            len(rgb_keys) == 1 and set(keywords) == rgb_keys | {"force_color"},
            "source_arguments_outside_rgb_review",
        )
        (name,) = rgb_keys
        control = keywords["force_color"]
        require(
            control["kind"] == "boolean" and control["value"] is True,
            "source_control_not_literal_true",
        )
        require(
            mapping["source_force_color_handling"] == CONTROL_HANDLING,
            "source_control_must_not_be_forwarded",
        )
        require(
            mapping["source_assertion_digest"] == case.assertion_digest,
            "source_assertion_identity_mismatch",
        )
        args = data["positional_args"]
        require(len(args) == 1 and args[0]["kind"] == "string", "source_text_literal_required")
        require(
            identical(mapping["source_positional_args"], args)
            and identical(mapping["proposed_target_positional_args"], args),
            "positional_literal_changed",
        )
        require(
            mapping["source_rgb_keyword"] == name
            and mapping["proposed_target_rgb_keyword"] == ROLES[name],
            "foreground_background_role_changed",
        )
        rgb = keywords[name]
        require(
            identical(mapping["source_rgb_literal"], rgb)
            and identical(mapping["proposed_target_rgb_literal"], rgb),
            "rgb_literal_changed",
        )
        require(
            case.oracle == "raises"
            and case.exception == "ValueError"
            and mapping["source_exception"] == case.exception
            and "exception_match" in data
            and mapping["preserved_exception_match"] == data["exception_match"],
            "source_oracle_changed_or_unsupported",
        )
        require(
            rgb["kind"] == "tuple"
            and len(rgb["items"]) in {2, 3, 4}
            and all(
                item["kind"] == "integer" and type(item["value"]) is int for item in rgb["items"]
            ),
            "rgb_domain_outside_review",
        )
        values = [item["value"] for item in rgb["items"]]
        require(
            len(values) != 3 or any(value < 0 or value > 255 for value in values),
            "rgb_domain_outside_review",
        )
        rows.append(
            {
                "source_case_id": case.case_id,
                "source_assertion_digest": case.assertion_digest,
                "target_positional_args": args,
                "target_keyword_args": [{"name": ROLES[name], "literal": rgb}],
                "source_only_control": {
                    "name": "force_color",
                    "literal": control,
                    "handling": CONTROL_HANDLING,
                },
                "preserved_oracle": {
                    "oracle": "raises",
                    "exception": case.exception,
                    "exception_match": data["exception_match"],
                },
                "input_shape": "three_integer_channels_out_of_range"
                if len(values) == 3
                else "malformed_integer_tuple_length",
            }
        )
    rows.sort(key=lambda row: row["source_case_id"])
    semantic = {
        "algorithm": ALGORITHM,
        "source_contract_digest": digest_bytes(contract_raw),
        "target": target,
        "rows": rows,
    }
    value = {
        "schema_version": "rgb-literal-mapping-audit.v1",
        "algorithm": ALGORITHM,
        "status": "syntax_consistent_review_required",
        "assurance": "payload_oracle_consistency_only_not_source_verification_or_semantics",
        "source_contract_id": contract.contract_id,
        "source_case_count": len(cases),
        "mapped_case_count": len(rows),
        "target": target,
        "rows": rows,
        "input_shape_counts": {
            shape: sum(row["input_shape"] == shape for row in rows)
            for shape in sorted({row["input_shape"] for row in rows})
        },
        "semantic_digest": digest_bytes(canonical_json_bytes(semantic)),
        "input_byte_digests": {
            "source_contract": digest_bytes(contract_raw),
            "worksheet": digest_bytes(worksheet_raw),
            "inspection": digest_bytes(inspection_raw),
        },
        "script_digest": digest_bytes(Path(__file__).read_bytes()),
        "source_evidence_guard_currently_verified": False,
        "mapping_semantics_approved": False,
        "labels_assigned": False,
        "execution_allowed": False,
        "target_execution_count": 0,
        "next_action": "Review lineage, normative behavior and witness design. Fresh source "
        "verification and a separately approved/versioned research bridge remain required. "
        "This audit cannot be used as a contract or an execution authorization.",
    }
    value["artifact_digest"] = digest_json_artifact(value)
    return value


def _read(path):
    reject_links(path)
    require(
        path.is_file() and path.stat().st_nlink == 1 and path.stat().st_size <= LIMIT,
        "input_missing_linked_or_oversized",
    )
    raw = path.read_bytes()
    require(len(raw) <= LIMIT, "input_missing_linked_or_oversized")
    return raw


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-contract", required=True, type=Path)
    parser.add_argument("--worksheet", required=True, type=Path)
    parser.add_argument("--target-inspection", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        reject_links(args.output)
        output = args.output.resolve()
        require(
            output.is_relative_to(Path.cwd().resolve()) and output != Path.cwd().resolve(),
            "output_must_be_below_current_workspace",
        )
        require(not output.exists(), "output_exists_choose_new_id")
        value = audit_mapping(
            _read(args.source_contract), _read(args.worksheet), _read(args.target_inspection)
        )
        write_immutable(output / "mapping-audit.json", canonical_json_bytes(value))
    except (
        OSError,
        ValueError,
        KeyError,
        TypeError,
        RecursionError,
        AttributeError,
        ArtifactIntegrityError,
    ) as error:
        reason = str(error) if type(error) is MappingAuditError else "invalid_mapping_input"
        print(json.dumps({"status": "rejected", "reason_code": reason}))
        return 5
    print(canonical_json_bytes(value).decode())
    return 4  # A consistent mapping is still neither human approval nor permission to execute.


if __name__ == "__main__":
    raise SystemExit(main())
