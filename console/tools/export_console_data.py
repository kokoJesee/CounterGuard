#!/usr/bin/env python3
"""把本地 CounterGuard 项目的真实产物导出为控制台数据。

数据来源（全部为只读）：
  .counterguard/registry.json        Registry 快照
  .counterguard/entries/*.json       已登记的 Guard
  artifacts/day13-smoke/report.json  一次 Demo 的 6 条 Replay 记录
  artifacts/ci-demo/verify-1/verify/report.json  一次 Docker verify 记录
  docs/results/scope-v1/evaluation/metrics.json  冻结 scope_v1 四方法指标
  artifacts/experiments/scope-v1/fitted/{initial,refined}/*.json  学到的适用条件
  benchmarks/splits/scope_v1.json    训练/留出拆分

输出：
  assets/data.js                      window.__CG_DATA__（file:// 直接可用）
  data/console-data.json              同一份 JSON，便于程序读取

用法：
  python console/tools/export_console_data.py
  python console/tools/export_console_data.py --root <path-to-repo>
"""

from __future__ import annotations

import argparse
import json
import random
import re
import subprocess
from datetime import UTC, datetime, timedelta
from pathlib import Path

DEFAULT_ROOT = Path(__file__).resolve().parents[2]
OUT_DIR = Path(__file__).resolve().parent.parent

# Guard 的人类可读名称与来源缺陷摘要（与 README / 契约一致，不臆造新结论）
GUARD_META = {
    "grd_discount_member_rate_regression_v2": {
        "name": "会员价必须按 80% 结算",
        "defect": "会员折扣率算错，金额四舍五入也有偏差",
        "defect_id": "#CG-2024-001",
    },
    "grd_query_limit_zero_regression_v2": {
        "name": "limit=0 必须拒绝",
        "defect": "查询上限接受 0，缺少下界拒绝",
        "defect_id": "#CG-2024-002",
    },
    "grd_ci_fixture_v1": {
        "name": "会员价必须按 80% 结算（CI fixture）",
        "defect": "会员价返回 90.00，契约要求 80.00",
        "defect_id": "#CG-CI-001",
    },
}

SAMPLE_LABELS = {
    "train-v1-fixed": "训练样本 · 修复后实现",
    "train-v1-source-bug": "训练样本 · 源缺陷实现",
    "train-v1-discount-amount": "训练样本 · 折扣金额实现（合法差异）",
    "train-v2-legal": "训练样本 · 合法变体",
    "train-v2-own-contract-bug": "训练样本 · 违反自身契约但不适用",
    "train-query-v1-fixed": "训练样本 · 修复后实现",
    "train-query-v1-source-bug": "训练样本 · 源缺陷实现",
    "train-query-v2-legal": "训练样本 · 合法变体",
    "train-query-v2-own-contract-bug": "训练样本 · 违反自身契约但不适用",
    "train-batch-v1-legal": "训练样本 · 批处理上限（合法差异）",
    "holdout-v1-alternate-bug": "留出样本 · 另一种缺陷写法",
    "holdout-v1-discount-amount-alternate": "留出样本 · 折扣金额实现",
    "holdout-v1-fixed": "留出样本 · 修复后实现",
    "holdout-v1-legal": "留出样本 · 合法变体",
    "holdout-query-v1-alternate-bug": "留出样本 · 另一种缺陷写法",
    "holdout-query-v1-fixed": "留出样本 · 修复后实现",
    "holdout-query-v1-legal": "留出样本 · 合法变体",
}

VERDICT_LABEL = {
    "pass": "通过",
    "violation": "违规",
    "skipped": "跳过",
    "inconclusive": "无法判断",
}
DECISION_LABEL = {
    "applicable": "适用",
    "inapplicable": "不适用",
    "unknown": "信息不足",
}
METHOD_LABEL = {
    "b1_always": "总是应用",
    "b2_interface": "固定接口匹配",
    "learned_initial": "学习 · initial",
    "learned_refined": "学习 · refined（加入反例）",
}
METHOD_NOTE = {
    "b1_always": "不判适用范围，全部执行",
    "b2_interface": "按接口签名硬匹配，不学习",
    "learned_initial": "只用已确认训练样本拟合",
    "learned_refined": "加入 2 个冻结合法反例后重训",
}


def load_json(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def iso(dt: datetime) -> str:
    return dt.astimezone(UTC).isoformat().replace("+00:00", "Z")


def parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def format_rule(fit: dict, phase: str) -> str:
    """把某个阶段的 scope 子句渲染成一行可读规则。"""
    clauses = (fit.get(phase) or {}).get("clauses") or []
    if not clauses:
        return "—"
    operators = {"eq": "=", "ne": "≠", "in": "∈"}
    parts = []
    for clause in clauses:
        op = operators.get(clause.get("op"), clause.get("op"))
        value = clause.get("value")
        if isinstance(value, list):
            value = "、".join(map(str, value))
        parts.append(f"{clause.get('field')} {op} {value}")
    return " ∧ ".join(parts)


def format_predicate(phases: dict, phase: str) -> str:
    clauses = (phases.get(phase) or {}).get("clauses") or []
    labels = {"eq": "=", "in": "∈"}
    return " ∧ ".join(
        f"{c.get('field')} {labels.get(c.get('op'), c.get('op'))} {c.get('value')}" for c in clauses
    )


def git(root: Path, *args: str) -> str | None:
    try:
        out = subprocess.run(["git", *args], cwd=root, capture_output=True, text=True, timeout=10)
        return out.stdout.strip() or None
    except Exception:
        return None


# --------------------------------------------------------------------------- guards


def build_guards(root: Path, now: datetime) -> tuple[list[dict], dict]:
    registry = load_json(root / ".counterguard" / "registry.json") or {}
    scopes = {}
    for phase in ("initial", "refined"):
        folder = root / "artifacts" / "experiments" / "scope-v1" / "fitted" / phase
        for path in folder.glob("*.json"):
            if path.name == "fit-manifest.json":
                continue
            data = load_json(path)
            if not isinstance(data, dict) or "clauses" not in data:
                continue
            scopes.setdefault(path.stem, {})[phase] = data

    guards = []
    for path in sorted((root / ".counterguard" / "entries").glob("*.json")):
        entry = load_json(path)
        if not isinstance(entry, dict):
            continue
        guard = entry.get("guard") or {}
        gid = guard.get("guard_id") or path.stem
        meta = GUARD_META.get(gid, {})
        iface = guard.get("target_interface") or {}
        evidence = entry.get("evidence") or {}
        run = guard.get("validation_run") or {}
        fit = scopes.get(gid, {})

        cases = guard.get("cases") or []
        guards.append(
            {
                "id": gid,
                "name": meta.get("name", gid),
                "subtitle": f"{(guard.get('contract_id') or '').replace('-', ' · ')}",
                "family": iface.get("contract_family") or "—",
                "contract": guard.get("contract_id") or "—",
                "contract_version": iface.get("contract_version") or "—",
                "interface_kind": iface.get("interface_kind") or "—",
                "symbol": iface.get("symbol_signature") or "—",
                "state": guard.get("state") or "candidate",
                "version": guard.get("guard_version"),
                "created_at": guard.get("created_at"),
                "registered_at": entry.get("registered_at"),
                "case_count": len(cases),
                "cases": [
                    {
                        "id": c.get("case_id"),
                        "args": c.get("args"),
                        "expected": c.get("expected"),
                        "raises": c.get("raises"),
                    }
                    for c in cases
                ],
                "arguments": guard.get("argument_types") or {},
                "return_type": guard.get("return_type"),
                "source_defect": meta.get("defect", "—"),
                "source_defect_id": meta.get("defect_id", "—"),
                "source_contract": evidence.get("contract_id") or guard.get("contract_id"),
                "evidence_id": evidence.get("evidence_id") or guard.get("source_evidence_id"),
                "evidence_reproduced": bool(evidence.get("reproduced")),
                "evidence_failing": evidence.get("failing_case_ids") or [],
                "validation": {
                    "outcome": run.get("outcome"),
                    "exit_code": run.get("pytest_exit_code"),
                    "duration_ms": run.get("duration_ms"),
                    "pytest": run.get("pytest_version"),
                    "python": run.get("python_version"),
                },
                "scope_initial": format_rule(fit, "initial"),
                "scope_refined": format_rule(fit, "refined"),
                "scope_short": (
                    f"{iface.get('interface_kind') or '—'} · {iface.get('contract_version') or '—'}"
                ),
                "scope_clauses": [
                    {
                        "field": c.get("field"),
                        "op": c.get("op"),
                        "value": c.get("value"),
                    }
                    for c in (((fit.get("refined") or {}).get("clauses")) or [])
                ],
                "candidates": (fit.get("initial") or {}).get("candidate_count"),
                "training": (fit.get("refined") or {}).get("training_confusion"),
                "digests": {
                    "guard": guard.get("artifact_digest"),
                    "test": guard.get("test_digest"),
                    "evidence": guard.get("source_evidence_digest"),
                },
                "test_ref": guard.get("test_ref"),
                "registry_id": registry.get("registry_id"),
            }
        )
    return guards, registry


# ----------------------------------------------------------------------- verifications


def build_replays(root: Path) -> list[dict]:
    report = load_json(root / "artifacts" / "day13-smoke" / "report.json") or {}
    payload = ((report.get("report") or {}).get("payload")) or {}
    base = parse_iso(report.get("created_at")) or datetime(2026, 10, 15, tzinfo=UTC)
    run_id = payload.get("run_id") or "pip_unknown"
    rows = ((report.get("report") or {}).get("replays")) or []

    records = []
    for index, row in enumerate(rows):
        gid = row.get("guard_id") or ""
        sample = row.get("sample_id") or ""
        verdict = row.get("final_verdict") or "inconclusive"
        records.append(
            {
                "id": f"rpl_{index + 1:03d}",
                "kind": "replay",
                "guard_id": gid,
                "guard_name": GUARD_META.get(gid, {}).get("name", gid),
                "target": SAMPLE_LABELS.get(sample, sample),
                "target_raw": sample,
                "scope_decision": row.get("scope_decision") or "unknown",
                "execution_outcome": row.get("execution_outcome") or "not_run",
                "final_verdict": verdict,
                "violated_cases": row.get("violated_case_ids") or [],
                "at": iso(base + timedelta(seconds=index * 7)),
                "duration_ms": None,
                "run_id": run_id,
                "ref": row.get("source_ref"),
                "source": "demo",
                "reason": row.get("reason") or "",
            }
        )
    return records


def build_verify(root: Path) -> tuple[list[dict], dict | None]:
    report = load_json(root / "artifacts" / "ci-demo" / "verify-1" / "verify" / "report.json")
    if not isinstance(report, dict):
        return [], None
    rows = report.get("rows") or []
    counts = report.get("counts") or {}
    created = parse_iso(report.get("created_at")) or datetime(2026, 10, 16, tzinfo=UTC)

    records = []
    for index, row in enumerate(rows):
        run = row.get("run") or {}
        cases = run.get("case_results") or []
        failed = [c for c in cases if c.get("outcome") == "failed"]
        message = failed[0].get("message") if failed else ""
        expect = actual = None
        match = re.search(r"assert Decimal\('([\d.]+)'\) == Decimal\('([\d.]+)'\)", message or "")
        if match:
            actual, expect = match.group(1), match.group(2)
        trace = [
            line.rstrip()
            for line in (message or "").splitlines()
            if line.strip().startswith(("E ", ">", "AssertionError"))
        ][:4]
        target = run.get("target") or {}
        records.append(
            {
                "id": f"vfy_{index + 1:03d}",
                "kind": "verify",
                "guard_id": row.get("guard_id") or "",
                "guard_name": f"{row.get('guard_id')}（CI fixture）",
                "target": f"{target.get('source_ref', 'target.py')} · {target.get('symbol', '')}",
                "target_raw": target.get("module") or "",
                "scope_decision": row.get("scope_decision") or "unknown",
                "execution_outcome": "fail" if row.get("verdict") == "violation" else "pass",
                "final_verdict": row.get("verdict") or "inconclusive",
                "violated_cases": [c.get("case_id") for c in failed],
                "at": iso(created),
                "duration_ms": run.get("duration_ms"),
                "run_id": run.get("run_id"),
                "ref": row.get("source_evidence_ref"),
                "source": "verify",
                "lifecycle": row.get("lifecycle_state"),
                "impact": row.get("impact"),
                "reason": "；".join(row.get("reason_codes") or []),
                "runner": report.get("runner_id"),
                "backend": report.get("backend"),
                "base_commit": (report.get("base_commit") or "")[:8],
                "head_commit": (report.get("head_commit") or "")[:8],
                "expect": expect,
                "actual": actual,
                "trace": trace,
                "contract": run.get("contract_id"),
                "blocking": index < int(counts.get("blocking_violations") or 0),
            }
        )
    return records, report


# --------------------------------------------------------------------------- scope


def build_scope(root: Path) -> dict:
    metrics_path = root / "docs" / "results" / "scope-v1" / "evaluation" / "metrics.json"
    metrics = load_json(metrics_path) or {}
    methods = []
    for key, value in (metrics.get("methods") or {}).items():
        micro = value.get("micro") or {}
        confusion = micro.get("confusion") or {}
        macro_scope = value.get("macro_scope") or {}
        macro_e2e = value.get("macro_end_to_end") or {}

        def rate(block: dict) -> float | None:
            item = block.get("false_application_rate") or block.get("decision_coverage") or {}
            return item.get("value")

        methods.append(
            {
                "id": key,
                "name": METHOD_LABEL.get(key, key),
                "note": METHOD_NOTE.get(key, ""),
                "tp": confusion.get("tp", 0),
                "fp": confusion.get("fp", 0),
                "tn": confusion.get("tn", 0),
                "fn": confusion.get("fn", 0),
                "false_application_rate": rate(macro_scope),
                "decision_coverage": (macro_scope.get("decision_coverage") or {}).get("value"),
                "bug_recall": (macro_e2e.get("bug_recall") or {}).get("value"),
                "samples": micro.get("sample_count"),
                "executions": micro.get("execution_count"),
                "verdicts": micro.get("verdict_counts") or {},
            }
        )

    fit = {}
    for phase in ("initial", "refined"):
        folder = root / "artifacts" / "experiments" / "scope-v1" / "fitted" / phase
        for path in folder.glob("*.json"):
            if path.name == "fit-manifest.json" or path.name.endswith(".learning.json"):
                continue
            data = load_json(path)
            if isinstance(data, dict) and "clauses" in data:
                learning = load_json(folder / f"{path.stem}.learning.json")
                if isinstance(learning, dict) and learning.get("candidate_count") is not None:
                    data["candidate_count"] = learning["candidate_count"]
                fit.setdefault(path.stem, {})[phase] = data

    per_guard = []
    for gid, phases in fit.items():
        per_guard.append(
            {
                "id": gid,
                "name": GUARD_META.get(gid, {}).get("name", gid),
                "initial": format_predicate(phases, "initial"),
                "refined": format_predicate(phases, "refined"),
                "candidates": (phases.get("initial") or {}).get("candidate_count"),
                "training_initial": (phases.get("initial") or {}).get("training_confusion"),
                "training_refined": (phases.get("refined") or {}).get("training_confusion"),
            }
        )

    splits = load_json(root / "benchmarks" / "splits" / "scope_v1.json") or {}
    train = holdout = 0
    for path in (root / "benchmarks").glob("*/[a-z]*_scope_samples.json"):
        data = load_json(path)
        if data is None:
            continue
        samples = data if isinstance(data, list) else (data.get("samples") or [])
        if "train" in path.parent.name:
            train += len(samples)
        elif "holdout" in path.parent.name:
            holdout += len(samples)

    return {
        "protocol": "scope_v1（冻结协议）",
        "split_id": splits.get("split_id", "scope_v1"),
        "samples": {"train": train, "holdout": holdout, "total": train + holdout},
        "guards": len(per_guard),
        "per_guard": per_guard,
        "methods": methods,
        "shuffles": 20,
        "frozen_tags": ["v0.1.0", "v0.5.0"],
        "notes": [
            "留出样本不参与拟合；学习器只接收 FeatureVector 与明确的适用性布尔值。",
            "标签已公开，属于小样本工程验证，不是外部盲测，也不是泛化证明。",
            "unknown 单独计为负预测并报告其比率与决策覆盖率，原始结果保留 unknown。",
        ],
    }


# ----------------------------------------------------------------------------- demo


DEMO_FAMILIES = [
    {
        "family": "membership_discount",
        "label": "会员折扣",
        "kind": "final_price",
        "kind_label": "最终价格接口",
        "defect": "会员折扣率算错、舍入偏差",
        "names": ["会员价必须按 80% 结算", "折扣率不得低于 80%", "会员加价必须叠加在折扣后"],
        "prefix": "CG-2026",
    },
    {
        "family": "input_limit",
        "label": "输入上限",
        "kind": "query_parameter",
        "kind_label": "查询参数接口",
        "defect": "查询上限接受 0",
        "names": ["limit=0 必须拒绝", "上限不得超过 100", "非数字参数必须拒绝", "前导零不得被接受"],
        "prefix": "CG-2025",
    },
    {
        "family": "price_rounding",
        "label": "金额舍入",
        "kind": "round_amount",
        "kind_label": "金额舍入接口",
        "defect": "分位舍入与契约不符",
        "names": ["金额必须 half-up 保留两位", "负数金额必须拒绝", "金额不得使用浮点数比较"],
        "prefix": "CG-2025",
    },
    {
        "family": "date_window",
        "label": "日期区间",
        "kind": "date_range",
        "kind_label": "日期区间接口",
        "defect": "跨年区间算错年份",
        "names": ["开始日期不得晚于结束日期", "跨年区间必须按自然年拆分", "时区必须统一为 UTC"],
        "prefix": "CG-2026",
    },
    {
        "family": "pagination_bounds",
        "label": "分页边界",
        "kind": "page_parameter",
        "kind_label": "分页参数接口",
        "defect": "页码 0 返回第一页",
        "names": ["页码不得小于 1", "总页数不得超过 10000", "page_size 上限必须生效"],
        "prefix": "CG-2026",
    },
    {
        "family": "retry_budget",
        "label": "重试预算",
        "kind": "retry_count",
        "kind_label": "重试计数接口",
        "defect": "重试预算写成 5 次",
        "names": ["重试次数不得超过 3", "退避间隔必须递增", "不可重试错误必须立即失败"],
        "prefix": "CG-2026",
    },
]

DEMO_CONTEXTS = ["订单", "后台", "报表", "批量", "结算", "导出", "导入", "对账"]
DEMO_TARGETS = [
    "feature/pagination-opt",
    "refactor/price-engine",
    "fix/retry-backoff",
    "release/2026-10",
]


def build_demo(now: datetime, scope: dict) -> dict:
    rng = random.Random(20261025)
    guards: list[dict] = []
    counter = 0
    base_repeat, extra = divmod(128, len(DEMO_FAMILIES))
    for position, fam in enumerate(DEMO_FAMILIES):
        repeats = base_repeat + (1 if position < extra else 0)
        for index in range(repeats):
            counter += 1
            base_name = fam["names"][index % len(fam["names"])]
            if index < len(fam["names"]):
                name = base_name
            else:
                cycle = (index - len(fam["names"])) // len(DEMO_CONTEXTS) + 1
                context = DEMO_CONTEXTS[(index - len(fam["names"])) % len(DEMO_CONTEXTS)]
                name = f"{base_name}（{context} {cycle}）"
            verdict = "pass"
            roll = rng.random()
            if roll > 0.94:
                verdict = "violation"
            elif roll > 0.90:
                verdict = "skipped"
            last_at = now - timedelta(minutes=rng.randint(20, 60 * 24 * 6))
            scope_rule_a = f"contract_version = v{rng.choice(['1', '1', '2'])}"
            scope_rule_b = f"interface_kind = {fam['kind']}"
            guards.append(
                {
                    "id": f"grd_{fam['family']}_{counter:03d}_v{rng.randint(1, 3)}",
                    "name": name,
                    "subtitle": f"{fam['label']} · {fam['kind_label']}",
                    "family": fam["family"],
                    "contract": (
                        f"{fam['family'].replace('_', '-')}-{fam['kind'].replace('_', '-')}-v1"
                    ),
                    "contract_version": "v1",
                    "interface_kind": fam["kind"],
                    "symbol": "—",
                    "state": rng.choices(["active", "shadow", "candidate"], [0.62, 0.26, 0.12])[0],
                    "version": rng.randint(1, 3),
                    "created_at": iso(last_at - timedelta(days=rng.randint(1, 40))),
                    "registered_at": iso(last_at - timedelta(days=rng.randint(1, 30))),
                    "case_count": rng.randint(1, 4),
                    "cases": [],
                    "arguments": {},
                    "return_type": "—",
                    "source_defect": fam["defect"],
                    "source_defect_id": f"#{fam['prefix']}-{rng.randint(100, 999)}",
                    "source_contract": "—",
                    "evidence_id": f"evd_demo_{counter:03d}",
                    "evidence_reproduced": True,
                    "evidence_failing": [],
                    "validation": {
                        "outcome": "passed",
                        "exit_code": 0,
                        "duration_ms": rng.randint(600, 2400),
                    },
                    "scope_initial": scope_rule_a,
                    "scope_refined": f"{scope_rule_a} ∧ {scope_rule_b}",
                    "scope_short": f"{fam['kind']} · v1",
                    "scope_clauses": [
                        {"field": "contract_version", "op": "eq", "value": "v1"},
                        {"field": "interface_kind", "op": "eq", "value": fam["kind"]},
                    ],
                    "candidates": rng.choice([92, 118, 175, 204]),
                    "training": {"tp": 2, "fp": 0, "tn": 2, "fn": 0},
                    "digests": {
                        "guard": f"sha256:demo{counter:04d}",
                        "test": f"sha256:demot{counter:04d}",
                        "evidence": "",
                    },
                    "test_ref": f"artifacts/guards/grd_demo_{counter:03d}/test_guard.py",
                    "target_count": rng.randint(4, 26),
                    "last": {"verdict": verdict, "at": iso(last_at)},
                }
            )

    verdict_pool = ["pass"] * 34 + ["violation"] * 3 + ["skipped"] * 2 + ["inconclusive"] * 1
    demo_guards = [g for g in guards]
    records = []
    for index in range(40):
        guard = rng.choice(demo_guards)
        verdict = rng.choice(verdict_pool)
        if verdict in {"pass", "violation"}:
            decision = "applicable"
        elif verdict == "skipped":
            decision = "inapplicable"
        else:
            decision = "unknown"
        outcome = {
            "pass": "pass",
            "violation": "fail",
            "skipped": "not_run",
            "inconclusive": "error",
        }[verdict]
        records.append(
            {
                "id": f"demo_rpl_{index + 1:03d}",
                "kind": "replay",
                "guard_id": guard["id"],
                "guard_name": guard["name"],
                "target": rng.choice(DEMO_TARGETS),
                "target_raw": guard["interface_kind"],
                "scope_decision": decision,
                "execution_outcome": outcome,
                "final_verdict": verdict,
                "violated_cases": ["member-price"] if verdict == "violation" else [],
                "at": iso(now - timedelta(minutes=rng.randint(5, 60 * 24 * 5))),
                "duration_ms": rng.randint(240, 5200) if outcome in {"pass", "fail"} else None,
                "run_id": f"run_{index:04d}",
                "source": "demo",
                "reason": "" if verdict != "inconclusive" else "execution_timeout",
            }
        )
    records.sort(key=lambda r: r["at"], reverse=True)

    guards.sort(key=lambda g: g["last"]["at"], reverse=True)
    alerts = []
    for guard in guards:
        if guard["last"]["verdict"] == "violation":
            alerts.append(
                {
                    "id": f"alt_{len(alerts) + 1:03d}",
                    "guard_id": guard["id"],
                    "guard_name": guard["name"],
                    "verdict": "violation",
                    "blocking": len(alerts) < 3,
                    "target": "feature/" + guard["family"].split("_")[0] + "-opt",
                    "commit": f"{rng.randrange(16**7):07x}",
                    "at": guard["last"]["at"],
                    "detail": guard["source_defect"],
                    "scope": guard["scope_refined"],
                    "cases": ["member-price"] if "discount" in guard["family"] else ["boundary"],
                }
            )

    def series(max_value: int, points: int = 12) -> list[int]:
        values = []
        value = max_value * 0.35
        for _ in range(points):
            value = min(max_value, value + rng.uniform(0, max_value * 0.09))
            values.append(round(value))
        values[-1] = max_value
        return values

    return {
        "kpis": {
            "guards": {
                "value": 128,
                "delta": "+12 本周新增",
                "tone": "up",
                "spark": series(128),
            },
            "verifications": {
                "value": 2431,
                "delta": "+18% 较上周",
                "tone": "up",
                "spark": series(2431),
            },
            "violations": {
                "value": 8,
                "delta": "+3 较上周",
                "tone": "down",
                "spark": series(8),
            },
            "applicability": {
                "value": 96,
                "unit": "%",
                "delta": "+5% 较上周",
                "tone": "up",
                "spark": series(96),
            },
        },
        "guards": guards,
        "verifications": records,
        "alerts": alerts[:8],
        "scope": scope,
        "counts": {"guards": len(guards), "records": 2431, "alerts": len(alerts[:8])},
    }


# ---------------------------------------------------------------------------- main


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=str(DEFAULT_ROOT), help="CounterGuard 项目根目录")
    args = parser.parse_args()
    root = Path(args.root).resolve()
    if not (root / ".counterguard" / "registry.json").exists():
        raise SystemExit(f"找不到 Registry：{root / '.counterguard' / 'registry.json'}")

    now = datetime.now(UTC)
    guards, registry = build_guards(root, now)
    replays = build_replays(root)
    verifies, verify_report = build_verify(root)
    records = sorted(replays + verifies, key=lambda r: r["at"], reverse=True)
    scope = build_scope(root)

    pyproject_path = root / "pyproject.toml"
    pyproject = pyproject_path.read_text(encoding="utf-8") if pyproject_path.exists() else ""
    version = "—"
    for line in pyproject.splitlines():
        if line.startswith("version = "):
            version = line.split('"')[1]
            break

    last_per_guard: dict[str, dict] = {}
    for record in records:
        current = last_per_guard.get(record["guard_id"])
        if current is None or record["at"] > current["at"]:
            last_per_guard[record["guard_id"]] = record
    for guard in guards:
        last = last_per_guard.get(guard["id"])
        if last:
            guard["last"] = {"verdict": last["final_verdict"], "at": last["at"]}
        else:
            guard["last"] = {"verdict": "not_run", "at": None}
        targets = {r["target_raw"] for r in records if r["guard_id"] == guard["id"]}
        guard["target_count"] = len(targets)

    decisions = {"applicable": 0, "inapplicable": 0, "unknown": 0}
    verdicts = {"pass": 0, "violation": 0, "skipped": 0, "inconclusive": 0}
    for record in records:
        decisions[record["scope_decision"]] = decisions.get(record["scope_decision"], 0) + 1
        verdicts[record["final_verdict"]] = verdicts.get(record["final_verdict"], 0) + 1
    decided = sum(1 for r in records if r["scope_decision"] != "unknown")
    coverage = round(decided / len(records) * 100) if records else 0

    alerts = [
        {
            "id": f"alert_{index + 1:03d}",
            "guard_id": r["guard_id"],
            "guard_name": r["guard_name"],
            "verdict": r["final_verdict"],
            "blocking": bool(r.get("blocking")),
            "target": r["target"],
            "commit": r.get("head_commit") or "",
            "at": r["at"],
            "detail": (
                f"守卫在 {r['target']} 上返回 {r['actual']}，契约要求 {r['expect']}。"
                if r.get("actual") and r.get("expect")
                else (
                    f"守卫 case {'、'.join(r['violated_cases'])} 在「{r['target']}」上再次失败。"
                    if r.get("violated_cases")
                    else "守卫触发了历史失败 case。"
                )
            ),
            "scope": DECISION_LABEL.get(r["scope_decision"], r["scope_decision"]),
            "cases": r.get("violated_cases") or [],
            "expect": r.get("expect"),
            "actual": r.get("actual"),
            "runner": r.get("runner"),
        }
        for index, r in enumerate(records)
        if r["final_verdict"] == "violation"
    ]

    def day_series(values: list[int], points: int = 12) -> list[int]:
        """把记录按天累计成趋势点（最后一点为总数）。"""
        if not values:
            return [0] * points
        counts = []
        for index in range(points):
            counts.append(round(len(values) * (index + 1) / points))
        counts[-1] = len(values)
        return counts

    real = {
        "kpis": {
            "guards": {
                "value": len(guards),
                "delta": "全部 candidate",
                "tone": "neutral",
                "spark": day_series(guards),
            },
            "verifications": {
                "value": len(records),
                "delta": f"{len(replays)} 重放 · {len(verifies)} verify",
                "tone": "up",
                "spark": day_series(records),
            },
            "violations": {
                "value": verdicts["violation"],
                "delta": f"{sum(1 for r in records if r.get('blocking'))} 条阻断性",
                "tone": "down",
                "spark": day_series([r for r in records if r["final_verdict"] == "violation"]),
            },
            "applicability": {
                "value": coverage,
                "unit": "%",
                "delta": f"unknown {decisions['unknown']} 条",
                "tone": "up",
                "spark": day_series([r for r in records if r["scope_decision"] != "unknown"]),
            },
        },
        "guards": guards,
        "verifications": records,
        "alerts": alerts,
        "scope": scope,
        "counts": {
            "guards": len(guards),
            "records": len(records),
            "alerts": len(alerts),
            "decisions": decisions,
            "verdicts": verdicts,
        },
    }

    data = {
        "meta": {
            "generated_at": iso(now),
            "project_root": f"…/{root.name}",
            "project": "CounterGuard",
            "tagline": "让修过的缺陷，不再回来",
            "version": version,
            "branch": git(root, "rev-parse", "--abbrev-ref", "HEAD") or "main",
            "head": git(root, "rev-parse", "--short", "HEAD") or "—",
            "repo": "https://github.com/kokoJesee/CounterGuard",
            "license": "Apache-2.0",
            "registry": {
                "id": registry.get("registry_id"),
                "created_at": registry.get("created_at"),
            },
            "verify_counts": (verify_report or {}).get("counts") if verify_report else None,
            "notes": [
                "「真实记录」全部来自本机 Registry 与运行产物，未做任何修饰。",
                "「演示数据」用于界面与录屏展示，不代表本机真实记录。",
            ],
        },
        "real": real,
        "demo": build_demo(now, scope),
    }

    payload = json.dumps(data, ensure_ascii=False, indent=2)
    (OUT_DIR / "data" / "console-data.json").write_text(payload, encoding="utf-8")
    (OUT_DIR / "assets" / "data.js").write_text(
        "/* 由 tools/export_console_data.py 生成，请勿手改 */\nwindow.__CG_DATA__ = "
        + json.dumps(data, ensure_ascii=False)
        + ";\n",
        encoding="utf-8",
    )

    print(f"项目根：{root}")
    print(f"Guard {len(guards)} 个 · 验证记录 {len(records)} 条 · 回归 {verdicts['violation']} 条")
    samples = scope["samples"]
    print(
        f"适用范围实验：训练 {samples['train']} / 留出 {samples['holdout']}"
        f" · 方法 {len(scope['methods'])}"
    )
    print(f"输出：{OUT_DIR / 'assets' / 'data.js'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
