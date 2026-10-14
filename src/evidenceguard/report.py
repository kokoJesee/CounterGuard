"""Render evaluation JSON facts; do not execute targets or compute new metrics."""

from evidenceguard.evaluation_metrics import METHOD_ORDER, EvaluationMetrics, Metric


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
