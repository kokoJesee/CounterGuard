"""Render JSON facts without executing targets or changing their conclusions."""

import json
from enum import StrEnum
from typing import Literal, Self

from pydantic import JsonValue, model_validator

from evidenceguard.evaluation_metrics import METHOD_ORDER, EvaluationMetrics, Metric
from evidenceguard.models import ArtifactRef, FrozenModel, RunOutcome


class OutputFormat(StrEnum):
    TEXT = "text"
    JSON = "json"
    MARKDOWN = "markdown"


class ReplayPresentation(FrozenModel):
    guard_id: str
    sample_id: str | None = None
    source_ref: ArtifactRef | None = None
    scope_decision: Literal["applicable", "inapplicable", "unknown"]
    execution_outcome: Literal["not_run", "pass", "fail", "error", "timeout"]
    final_verdict: Literal["pass", "violation", "skipped", "inconclusive"]
    raw_outcome: RunOutcome | None
    raw_verdict: str
    reason: str | None = None
    violated_case_ids: tuple[str, ...] = ()
    decision_trace: tuple[dict[str, JsonValue], ...] = ()

    @model_validator(mode="after")
    def consistent_states(self) -> Self:
        execution, verdict = replay_states(self.scope_decision, self.raw_outcome, self.raw_verdict)
        if (self.execution_outcome, self.final_verdict) != (execution, verdict):
            raise ValueError("Presentation contradicts raw scope/execution/verdict")
        if self.scope_decision == "unknown" and not self.reason:
            raise ValueError("Unknown must retain its explanation")
        if self.final_verdict != "violation" and self.violated_case_ids:
            raise ValueError("Only violations may name failed cases")
        return self


def replay_states(scope: str, outcome: RunOutcome | None, verdict: str) -> tuple[str, str]:
    """A display projection, never an alternative applicability or execution oracle."""
    execution = (
        "not_run"
        if outcome is None
        else "pass"
        if outcome is RunOutcome.PASSED
        else "fail"
        if outcome is RunOutcome.TEST_FAILED
        else "timeout"
        if outcome is RunOutcome.TIMEOUT
        else "error"
    )
    if scope in {"inapplicable", "unknown"}:
        expected = "skipped_unknown" if scope == "unknown" else "skipped_inapplicable"
        if outcome is not None or verdict != expected:
            raise ValueError("Skipped decisions require their original verdict and no run")
        return execution, "skipped"
    if scope != "applicable":
        raise ValueError("Invalid scope decision")
    expected = {
        "pass": "pass",
        "violation": "fail",
        "timeout": "timeout",
        "execution_error": "error",
        "collection_error": "error",
    }
    if verdict == "stale":
        return execution, "inconclusive"
    if verdict not in expected or execution != expected[verdict]:
        raise ValueError("Replay verdict contradicts actual execution")
    return execution, {"pass": "pass", "violation": "violation"}.get(verdict, "inconclusive")


def present_replay(payload: dict, *, sample_id=None, source_ref=None) -> ReplayPresentation:
    run = payload["run"]
    outcome = RunOutcome(run["outcome"]) if run is not None else None
    execution, verdict = replay_states(payload["scope_decision"], outcome, payload["verdict"])
    return ReplayPresentation(
        guard_id=payload["guard_id"],
        sample_id=sample_id,
        source_ref=source_ref,
        scope_decision=payload["scope_decision"],
        execution_outcome=execution,
        final_verdict=verdict,
        raw_outcome=outcome,
        raw_verdict=payload["verdict"],
        reason=payload["error_detail"],
        violated_case_ids=tuple(payload["violated_case_ids"]),
        decision_trace=tuple(payload["decision_trace"]),
    )


class CommandReport(FrozenModel):
    schema_version: Literal["command-report.v1"] = "command-report.v1"
    operation: Literal["capture", "compile", "learn", "replay", "evaluate", "demo"]
    payload: dict[str, JsonValue]
    replays: tuple[ReplayPresentation, ...] = ()

    @model_validator(mode="after")
    def replay_payload_agrees(self) -> Self:
        if self.operation == "replay" and self.replays != (present_replay(self.payload),):
            raise ValueError("Replay presentation must project its original payload")
        if self.operation not in {"replay", "demo"} and self.replays:
            raise ValueError("This operation has no replay decision")
        return self


def command_report(operation: str, payload: dict) -> CommandReport:
    rows = (present_replay(payload),) if operation == "replay" else ()
    return CommandReport(operation=operation, payload=payload, replays=rows)


def _cell(value: object) -> str:
    return (
        str(value)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace("|", "&#124;")
        .replace("\r", " ")
        .replace("\n", " ")
    )


def render_report(record, format: OutputFormat | str) -> str:
    """All three formats consume the same JSON model; no IO or fresh decisions."""
    format = OutputFormat(format)
    payload = record.model_dump(mode="json")
    if format is OutputFormat.JSON:
        return json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    report = payload.get("report", payload)
    markdown = format is OutputFormat.MARKDOWN
    lines = [("# " if markdown else "") + f"EvidenceGuard {report['operation']}", ""]
    if "pipeline" in payload:
        lines += [
            f"pipeline: {_cell(payload['pipeline']['ref'])}",
            f"artifact_digest: {payload['artifact_digest']}",
            "",
        ]
    lines += [
        "Command completion/acceptance is separate from individual test results.",
        "skipped and unknown are never counted as pass.",
        "",
    ]
    if report["operation"] == "demo":
        facts = report["payload"]
        lines += [
            f"scenario: {facts['scenario_id']}",
            f"run_id: {facts['run_id']}",
            f"demo accepted: {str(facts['accepted']).lower()}",
            f"Replay executions: {facts['replay_execution_count']}",
            f"verdict_counts: {json.dumps(facts['verdict_counts'], sort_keys=True)}",
            "",
        ]
    if report["replays"]:
        if markdown:
            lines += [
                "| Guard / sample | scope_decision | execution_outcome | final_verdict |"
                " raw_verdict | reason / failed cases |",
                "|---|---|---|---|---|---|",
            ]
        for row in report["replays"]:
            identity = row["guard_id"] + (" / " + row["sample_id"] if row["sample_id"] else "")
            cells = [
                identity,
                row["scope_decision"],
                row["execution_outcome"],
                row["final_verdict"],
                row["raw_verdict"],
                row["reason"] or ", ".join(row["violated_case_ids"]) or "-",
            ]
            lines.append(
                ("| " if markdown else "")
                + " | ".join(map(_cell, cells))
                + (" |" if markdown else "")
            )
        lines.append("")
    if report["operation"] == "demo":
        lines += [("## " if markdown else "") + "Scope refinement", ""]
        for group in report["payload"]["groups"]:
            lines.append(_cell(group["guard_id"]))
            lines.append("minimal failed cases: " + ", ".join(group["failed_case_ids"]))
            for phase in ("initial", "refined"):
                rule = " AND ".join(
                    f"{c['field']} {c['op']} {c['value']}" for c in group["rules"][phase]["clauses"]
                )
                lines.append(f"{phase}: {_cell(rule)}")
            for name, link in sorted(group["provenance"].items()):
                if isinstance(link, dict):
                    lines.append(f"{name}: {_cell(link['ref'])}")
            lines.append("")
        lines += ["Frozen training examples; not a new holdout evaluation.", ""]
    # Other commands retain every original payload fact. Escaping protects Markdown fences.
    facts = json.dumps(report["payload"], ensure_ascii=False, sort_keys=True, indent=2)
    if markdown:
        facts = facts.replace("`", "\\u0060").replace("<", "\\u003c").replace(">", "\\u003e")
        if report["operation"] != "demo":
            lines += ["## Facts", "", "```json", facts, "```", ""]
        for row in report["replays"]:
            lines += [f"### {_cell(row['guard_id'])} / {_cell(row['sample_id'] or '-')}", ""]
            for trace in row["decision_trace"]:
                lines.append(
                    f"- {_cell(trace['field'])} {_cell(trace['op'])} "
                    f"{_cell(trace['expected'])}; actual={_cell(trace['actual'])}; "
                    f"matched={trace['matched']}"
                )
            if row["source_ref"]:
                lines.append(f"- replay: {_cell(row['source_ref'])}")
            lines.append("")
    else:
        if report["operation"] != "demo":
            lines += ["Facts:", facts, ""]
        if report["replays"]:
            lines += [
                "Replay details:",
                json.dumps(report["replays"], ensure_ascii=False, sort_keys=True, indent=2),
                "",
            ]
    return "\n".join(lines)


def _value(metric: Metric) -> str:
    if metric.value is None:
        return f"null（{metric.reason}；分母 {metric.denominator:g}）"
    return f"{metric.value:.4f}（{metric.numerator:g}/{metric.denominator:g}）"


def render_evaluation(metrics: EvaluationMetrics, paired: dict, accepted: bool) -> str:
    lines = [
        "# Scope v1 四方法留出评测",
        "",
        f"验收：{'通过' if accepted else '未通过，保留原始结果'}。",
        "六行留出标签已公开；本结果是工程一致性验证，不是盲测或广泛泛化证据。",
        "",
        "## 作用域（micro）",
        "",
        "| 方法 | TP | FP | TN | FN | FAR | Recall | Unknown rate | Decision coverage |",
        "|---|---:|---:|---:|---:|---|---|---|---|",
    ]
    for method in METHOD_ORDER:
        data = metrics.methods[method].micro
        c = data.confusion
        lines.append(
            f"| {method} | {c.tp} | {c.fp} | {c.tn} | {c.fn} | "
            + " | ".join(
                _value(data.scope[key])
                for key in ("false_application_rate", "recall", "unknown_rate", "decision_coverage")
            )
            + " |"
        )
    lines.extend(
        [
            "",
            "## 端到端（micro，分母仅来自留出行）",
            "",
            "| 方法 | Bug recall | False alert rate | Applicable-clean pass rate |"
            " Execution validity | Infrastructure failure rate |",
            "|---|---|---|---|---|---|",
        ]
    )
    for method in METHOD_ORDER:
        data = metrics.methods[method].micro
        lines.append(
            f"| {method} | "
            + " | ".join(
                _value(data.end_to_end[key])
                for key in (
                    "bug_recall",
                    "false_alert_rate",
                    "applicable_clean_pass_rate",
                    "execution_validity",
                    "infrastructure_failure_rate",
                )
            )
            + " |"
        )
    lines.extend(
        [
            "",
            "## 每 Guard 与 macro",
            "",
            "| 方法 | Guard | FAR | Recall | Bug recall |",
            "|---|---|---|---|---|",
        ]
    )
    for method in METHOD_ORDER:
        data = metrics.methods[method]
        for guard, part in data.per_guard.items():
            lines.append(
                f"| {method} | {guard} | {_value(part.scope['false_application_rate'])} | "
                f"{_value(part.scope['recall'])} | {_value(part.end_to_end['bug_recall'])} |"
            )
        bug = data.macro_end_to_end["bug_recall"]
        lines.append(
            f"| {method} | macro（Bug recall 纳入：{', '.join(bug.included_guards)}） | "
            f"{_value(data.macro_scope['false_application_rate'])} | "
            f"{_value(data.macro_scope['recall'])} | {_value(bug)} |"
        )
    lines.extend(
        [
            "",
            "## initial → refined 配对",
            "",
            "| 样本 | initial | refined | 修正错误应用 | 保留适用 | 新 FN | 新 FP |",
            "|---|---|---|---|---|---|---|",
        ]
    )
    for row in paired["rows"]:
        flags = " | ".join(
            "是" if row[key] else "否"
            for key in (
                "corrected_false_application",
                "retained_applicable_case",
                "new_false_rejection",
                "new_false_application",
            )
        )
        lines.append(
            f"| {row['sample_id']} | {row['initial_decision']} | "
            f"{row['refined_decision']} | {flags} |"
        )
    lines.extend(
        [
            "",
            f"修正错误应用 {paired['totals']['corrected_false_applications']} 个；"
            f"保留适用样本 {paired['totals']['retained_applicable_cases']} 个；"
            f"新增 FN/FP {paired['totals']['new_false_rejections']}/"
            f"{paired['totals']['new_false_applications']}。",
            "",
            "来源缺陷复检另外保存于 source-checks.jsonl，不进入留出指标分母。",
            "跳过与 unknown 均未运行，不计为通过；真实执行身份和时间保存在原始 Replay。",
            "predictions/metrics 是确定性投影；新执行的 Replay/manifest 保留新的实际时间与身份。",
            "",
        ]
    )
    return "\n".join(lines)
