"""Read-only historical inventory and explicit tool-owned research fixture commands."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

METHODS = ("b1_always", "b2_interface", "learned_initial", "learned_refined")
PROTOCOL = "experiments/scope_v1.json"
SPLIT = "benchmarks/splits/scope_v1.json"
PUBLISHED = "docs/results/scope-v1/evaluation"
PROTOCOL_PIN = "sha256:1f401186a3f51c17e582dbbdc96f9324e47e128f90fcb91f29594690bc8daa3a"
SPLIT_PIN = "sha256:f04170d16cd6e54f09edcc4b1c3cdb39f84ce4dbd2928c5923da7ccc21cd0cef"
PUBLICATION_PIN = "sha256:154d19625e3f858d82235bb348c18b4cedf07f6b31bdeee70e8b4aad6399ad38"
EXPECTED_HOLDOUT = ((2, 4, 0, 0), (2, 2, 2, 0), (2, 2, 2, 0), (2, 0, 4, 0))
EXPECTED_ALERTS = (2, 1, 1, 0)
MAX_FILE_BYTES = 2 * 1024 * 1024
SOURCE_REFS = (
    "src/counterguard/protocol.py",
    "src/counterguard/scope.py",
    "src/counterguard/evaluation.py",
    "src/counterguard/evaluation_metrics.py",
    "src/counterguard/bootstrap_binding.py",
    "src/counterguard/standalone_capture.py",
    "src/counterguard/standalone_guard.py",
    "src/counterguard/standalone_replay.py",
)


class InventoryError(ValueError):
    """Published facts failed a bounded consistency check."""


def canonical(value: object) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode("utf-8")


def digest(raw: bytes) -> str:
    return "sha256:" + hashlib.sha256(raw).hexdigest()


def require(condition: bool, message: str) -> None:
    if not condition:
        raise InventoryError(message)


def _pairs(pairs):
    result = {}
    for key, value in pairs:
        require(key not in result, "Duplicate JSON key")
        result[key] = value
    return result


def _reject_constant(value):
    raise InventoryError("Nonfinite JSON number: " + value)


def decode(raw: bytes):
    try:
        return json.loads(raw, object_pairs_hook=_pairs, parse_constant=_reject_constant)
    except (UnicodeError, json.JSONDecodeError, RecursionError) as error:
        raise InventoryError("Invalid published JSON") from error


def read(root: Path, ref: str) -> bytes:
    parts = Path(ref).parts
    require(not Path(ref).is_absolute() and ".." not in parts, "Unsafe input reference")
    path = root / ref
    for parent in (path, *path.parents):
        if parent == root:
            break
        require(not parent.is_symlink() and not parent.is_junction(), "Linked input refused")
    require(path.resolve().is_relative_to(root), "Input escaped source root")
    require(path.is_file() and path.stat().st_size <= MAX_FILE_BYTES, "Missing/oversize input")
    raw = path.read_bytes()
    require(len(raw) <= MAX_FILE_BYTES, "Input grew beyond byte budget")
    return raw


def check_artifact(value: dict, schema: str, pin: str | None = None) -> None:
    require(value.get("schema_version") == schema, "Unsupported published schema")
    body = {key: item for key, item in value.items() if key != "artifact_digest"}
    actual = digest(canonical(body))
    require(value.get("artifact_digest") == actual, "Artifact digest mismatch")
    require(pin is None or pin == actual, "Frozen identity mismatch")


def confusion(rows: list[dict], decisions: list[bool]) -> dict[str, int]:
    counts = dict.fromkeys(("tp", "fp", "tn", "fn"), 0)
    for row, positive in zip(rows, decisions, strict=True):
        label = row["labels"]["guard_applicable"]
        require(type(label) is bool and type(positive) is bool, "Non-boolean applicability")
        counts[("tp" if label else "fp") if positive else ("fn" if label else "tn")] += 1
    return counts


def summarize(rows: list[dict]) -> dict:
    """Count observed assertions independently of the production metrics module."""
    counts = confusion(rows, [row["scope_decision"] == "applicable" for row in rows])
    bugs = alerts = false_alerts = nonbugs = runs = unknown = 0
    per_guard = {}
    for row in rows:
        applicable = row["labels"]["guard_applicable"]
        violation = row["labels"]["guard_violation"]
        require(
            (type(violation) is bool if applicable else violation is None),
            "Violation label contradicts applicability",
        )
        decision, verdict, outcome = (row[k] for k in ("scope_decision", "verdict", "run_outcome"))
        require(decision in {"applicable", "inapplicable", "unknown"}, "Unknown scope decision")
        if decision != "applicable":
            require(outcome is None and not row["violated_case_ids"], "Skipped row contains run")
            require(verdict == "skipped_" + decision, "Skipped row has a misleading verdict")
        else:
            require(
                (verdict == "pass" and outcome == "passed" and not row["violated_case_ids"])
                or (
                    verdict == "violation"
                    and outcome == "test_failed"
                    and bool(row["violated_case_ids"])
                ),
                "Published assertion result is inconsistent",
            )
        true_bug = applicable and violation
        alert = decision == "applicable" and verdict == "violation"
        bugs += bool(true_bug)
        alerts += bool(alert and true_bug)
        false_alerts += bool(alert and not true_bug)
        nonbugs += not true_bug
        runs += outcome is not None
        unknown += decision == "unknown"
        guard_counts = per_guard.setdefault(row["guard_id"], {"bug_count": 0, "detected": 0})
        guard_counts["bug_count"] += bool(true_bug)
        guard_counts["detected"] += bool(alert and true_bug)
    return {
        "confusion": counts,
        "sample_count": len(rows),
        "execution_count": runs,
        "unknown_count": unknown,
        "false_alert_rate": {"numerator": false_alerts, "denominator": nonbugs},
        "bug_recall": {"numerator": alerts, "denominator": bugs},
        "per_guard_bug_counts": dict(sorted(per_guard.items())),
    }


def paired_counts(initial: list[dict], refined: list[dict]) -> dict[str, int]:
    keyed = {(row["guard_id"], row["sample_id"]): row for row in initial}
    result = dict.fromkeys(
        (
            "corrected_false_applications",
            "retained_applicable_cases",
            "new_false_rejections",
            "new_false_applications",
        ),
        0,
    )
    for row in refined:
        before = keyed[(row["guard_id"], row["sample_id"])]
        a = before["scope_decision"] == "applicable"
        b = row["scope_decision"] == "applicable"
        label = row["labels"]["guard_applicable"]
        result["corrected_false_applications"] += (
            not label and a and row["scope_decision"] == "inapplicable"
        )
        result["retained_applicable_cases"] += label and a and b
        result["new_false_rejections"] += label and a and not b
        result["new_false_applications"] += not label and not a and b
    return result


def inventory(root: Path) -> dict:
    root = root.resolve(strict=True)
    inputs = {}

    def load(ref):
        raw = read(root, ref)
        inputs[ref] = digest(raw)
        return decode(raw)

    protocol, split = load(PROTOCOL), load(SPLIT)
    check_artifact(protocol, "experiment-protocol.v1", PROTOCOL_PIN)
    check_artifact(split, "split-manifest.v1", SPLIT_PIN)
    require(protocol["protocol_id"] == split["split_id"] == "scope_v1", "Unexpected study")
    bindings = {item["guard_id"]: item for item in protocol["guards"]}
    train, holdout = {}, {}
    for entry in split["files"]:
        ref = entry["path"]
        require(ref.startswith("benchmarks/" + entry["split"] + "/"), "Wrong dataset split")
        rows = load(ref)
        require(digest(canonical(rows)) == entry["content_digest"], "Dataset digest mismatch")
        target = train if entry["split"] == "train" else holdout
        for row in rows:
            key = (row["labels"]["guard_id"], row["sample_id"])
            require(key[0] == entry["guard_id"] and key not in target, "Duplicate/wrong data row")
            target[key] = row
    require(len(train) == 9 and len(holdout) == 6, "Frozen data counts differ")
    for guard, phases in split["phases"].items():
        require(
            {sample for gid, sample in train if gid == guard}
            == set(phases["initial"] + phases["refinement_additions"]),
            "Training phase membership differs",
        )
        require(
            {sample for gid, sample in holdout if gid == guard} == set(phases["holdout"]),
            "Holdout membership differs",
        )
    train_rows = list(train.values())
    train_counts = {
        "b1_always": confusion(train_rows, [True] * len(train_rows)),
        "b2_interface": confusion(
            train_rows,
            [
                row["features"]["interface_kind"]
                == bindings[row["labels"]["guard_id"]]["frozen_interface_kind"]
                for row in train_rows
            ],
        ),
    }
    require(train_counts == protocol["expected_train"], "Independent training count differs")
    manifest = load(PUBLISHED + "/manifest.json")
    metrics = load(PUBLISHED + "/metrics.json")
    paired = load(PUBLISHED + "/paired-refinement.json")
    check_artifact(manifest, "evaluation-report.v1", PUBLICATION_PIN)
    check_artifact(metrics, "evaluation-metrics.v1")
    require(manifest["protocol_digest"] == PROTOCOL_PIN, "Published protocol mismatch")
    require(manifest["split_digest"] == SPLIT_PIN, "Published split mismatch")
    raw = read(root, PUBLISHED + "/predictions.jsonl")
    inputs[PUBLISHED + "/predictions.jsonl"] = digest(raw)
    for name in ("metrics.json", "paired-refinement.json", "predictions.jsonl"):
        require(
            inputs[PUBLISHED + "/" + name] == manifest["files"][name], "Publication pin mismatch"
        )
    predictions = [decode(line) for line in raw.splitlines() if line.strip()]
    require(len(predictions) == manifest["prediction_count"] == 24, "Missing/extra predictions")
    grouped = {method: [] for method in METHODS}
    seen = set()
    for row in predictions:
        require(row["method"] in grouped, "Unknown method")
        key = (row["guard_id"], row["sample_id"])
        slot = (row["method"], *key)
        require(slot not in seen and key in holdout, "Duplicate/unrecognized prediction")
        require(row["labels"] == holdout[key]["labels"], "Prediction label differs from dataset")
        seen.add(slot)
        grouped[row["method"]].append(row)
    counts = {}
    for method, expected, false_alerts in zip(
        METHODS, EXPECTED_HOLDOUT, EXPECTED_ALERTS, strict=True
    ):
        require(len(grouped[method]) == 6, "Method omitted a holdout row")
        observed = summarize(grouped[method])
        require(tuple(observed["confusion"].values()) == expected, "Frozen holdout count differs")
        require(
            observed["false_alert_rate"] == {"numerator": false_alerts, "denominator": 5},
            "Frozen false-alert denominator/count differs",
        )
        recorded = metrics["methods"][method]["micro"]
        for key in ("confusion", "sample_count", "execution_count", "unknown_count"):
            require(observed[key] == recorded[key], "Published metric disagrees with raw rows")
        for key in ("false_alert_rate", "bug_recall"):
            ratio = recorded["end_to_end"][key]
            require(
                all(observed[key][k] == ratio[k] for k in ("numerator", "denominator")),
                "Published metric denominator disagrees with raw rows",
            )
        counts[method] = observed
    paired_observed = paired_counts(grouped["learned_initial"], grouped["learned_refined"])
    require(
        all(value == paired["totals"][key] for key, value in paired_observed.items()),
        "Published paired changes disagree with rows",
    )
    require(
        sum(item["execution_count"] for item in counts.values()) == manifest["execution_count"],
        "Published execution count differs",
    )
    for ref in SOURCE_REFS:
        inputs[ref] = digest(read(root, ref))
    report = {
        "schema_version": "scope-study-inventory.v1",
        "assurance": "published_fact_consistency_only_not_execution_provenance",
        "inventory_implementation_digest": digest(Path(__file__).read_bytes()),
        "input_digests": dict(sorted(inputs.items())),
        "protocol_digest": PROTOCOL_PIN,
        "split_digest": SPLIT_PIN,
        "train_counts": train_counts,
        "holdout_counts": counts,
        "paired_changes": paired_observed,
        "source_bug_checks": "historical_record_only_not_reexecuted",
        "target_execution_count": 0,
        "scope_v2_status": "not_implemented_or_frozen",
        "holdout_exposure": "scope_v1_public_no_scope_v2_labels_read",
        "execution_allowed": False,
    }
    report["artifact_digest"] = digest(canonical(report))
    return report


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    command = sub.add_parser("inventory", help="Independently recount published scope_v1 facts.")
    command.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    for name in ("audit", "replay", "verify"):
        research = sub.add_parser(
            name,
            help="Reviewed fixture research or external observations; never production.",
        )
        research.add_argument("--workspace", type=Path, required=True)
        research.add_argument("--source-repo", type=Path, required=True)
        research.add_argument("--target-repo", type=Path, required=True)
        research.add_argument("--review-digest", required=True)
        research.add_argument(
            "--fit-review-digest", help="Independent fit trust anchor for v2 only."
        )
        research.add_argument("--training-repository", type=Path, action="append", default=[])
        research.add_argument(
            "--result" if name == "verify" else "--plan", type=Path, required=True
        )
        if name == "replay":
            research.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    if args.command != "inventory":
        from counterguard.study_cli import execute_study_command

        return execute_study_command(args)
    try:
        result = inventory(args.root)
    except (InventoryError, OSError, KeyError, TypeError, ValueError) as error:
        reason = str(error) if type(error) is InventoryError else "Invalid or unavailable input"
        print(
            json.dumps({"status": "rejected", "error_type": type(error).__name__, "reason": reason})
        )
        return 5
    print(canonical(result).decode())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
