# CLI 与报告约定

源码开发版另有 [本地 Registry](registry.md)：`registry add/list/show/disable`；来源完整性失败退出 5，禁用是追加终态，不提升 Guard 生命周期。

Q1 的可执行只读入口为 `uv run counterguard preflight --repo <repo> --revision <sha>`，覆盖完整提交树及新旧 pytest TOML 配置；不 import/安装仓库。0 仅表示静态候选，blocked/unknown 退出 4、拒绝退出 5，均保持 execution_allowed=false。详见 [预检说明](preflight.md)。

日期：2026-10-15。格式版本为 `command-report.v1` / `demo-report.v1`。命令格式化不修改冻结 scope_v1 的标签、标准、公式或已发布记录。

## W3-A inspect

源码开发版新增 `inspect --repo ... --base ... --head ... --config ... --format json|text|markdown`，使用独立 `repository-inspection.v1`，不扩展旧 command-report.v1 或把候选影响当作 Replay verdict。完整可运行示例见 [只读仓库检查](repository-inspection.md)，安全准入见 [security-model.md](security-model.md)。

配置是严格 JSON 子集，即使扩展名为 .yaml。ready/unknown/rejected 分别退出 0/4/5；无效配置/修订语法退出 2。三格式同源，unknown 与拒绝保留原因。所有结果 execution_allowed=false / not_run，不能由 ready 推断可执行或测试通过。Frozen v0.1.0 wheel 不包含这个后续源码功能。

## 场景文件格式

**mvp.yaml 当前只能写 JSON 语法，不支持通用 YAML。** `.yaml` 后缀不会启用缩进映射、注释、锚点等 YAML 特性。请使用双引号、花括号和方括号，不加尾逗号；解析器使用现有 Pydantic JSON 入口，不引入 YAML 依赖。完整可用内容与会被拒绝的 YAML 反例见 [quickstart.md](quickstart.md)。语法不支持返回 2，在执行前拒绝。

标准 Demo 选择的六个冻结训练样本信息完整，所以原报告没有 unknown。独立的缺少 --contract 的真实 Replay 用法见 [quickstart.md](quickstart.md#怎么读结果以及为什么标准-demo-没有-unknown)：必须保留 unknown/not_run/skipped 和退出 4，不改动标准六行或评测分母。

## 命令与兼容

| 入口 | 原入口/含义 | 输出 |
|---|---|---|
| capture | 直接双向捕获，或 --request + recorded Gate | 未指定 --format 保持原 Evidence/Gate JSON |
| compile | 最小 Guard 编译与 fixed 自检 | 未指定 --format 保持原 Guard JSON |
| learn | scope learn 的同函数别名，train only | 未指定 --format 保持原 FitManifest JSON |
| replay run | 带 Scope 的真实重放；replay verify 保持只读审核 | run 支持格式选项；未指定时保持 ReplayResult JSON |
| evaluate | experiment evaluate 的同函数别名，holdout only | 未指定 --format 保持原 EvaluationReport JSON |
| demo | 离线 recorded Pipeline + 已验证事实报告 | 默认 text；持久化 JSON 与 Markdown；三格式同源 |

上表执行入口支持 `--format text|json|markdown`。显式格式统一为 CommandReport：operation、原始 payload、规范化 replays。原 artifact 的自摘要仍位于 payload 内，包装后的完整 JSON 不能当成 Evidence/Guard/ReplayResult 的原 schema 来加载。Demo 的完整 JSON 为 DemoReport（内含同一 CommandReport、真实创建时间、Pipeline 链接、展示代码摘要、自摘要），对应 `schemas/demo-report.schema.json`。

capture/compile/learn/evaluate 不是“新目标是否通过”的单行 Replay：它们的 replays 为空，不给出虚构 scope_decision。evaluate 的四方法完整事实/指标/Markdown 继续由 D9 不可变结果文件提供，CLI 格式选项仅展示原 EvaluationReport，不把验收摘要冒充逐行执行。

```powershell
uv run counterguard learn --protocol experiments/scope_v1.json --phase refined --output artifacts/fitted-new/refined --format markdown
uv run counterguard replay run --guard <guard.json> --scope <scope.json> --target <module:symbol> --contract <contract.json> --format json
uv run counterguard demo --scenario examples/demo/mvp.yaml --workspace artifacts/cli-demo-v1
uv run counterguard demo --workspace artifacts/cli-demo-v1 --format json
uv run counterguard demo --workspace artifacts/cli-demo-v1 --format markdown
uv run counterguard demo --workspace artifacts/cli-demo-v1 --verify-only
```

尖括号路径需要替换为同一来源链中的实际资产。不要混用旧 Guard 与新 fit 的摘要。已有失败、部分目录或代码/输入已变更时，选择新的 workspace 版本，不删除/重签原产物来恢复。

## 三个互相独立的状态

| 原始 Scope / Verdict / Run | scope_decision | execution_outcome | final_verdict |
|---|---|---|---|
| applicable / pass / passed | applicable | pass | pass |
| applicable / violation / test_failed | applicable | fail | violation |
| inapplicable / skipped_inapplicable / null | inapplicable | not_run | skipped |
| unknown / skipped_unknown / null | unknown | not_run | skipped |
| applicable / timeout / timeout | applicable | timeout | inconclusive |
| applicable / collection_error 或 execution_error / 执行异常 | applicable | error | inconclusive |
| applicable / stale / null 或实际 Run | applicable | not_run 或实际分类 | inconclusive |

raw_outcome 与 raw_verdict 不丢弃；unknown 保留具体原因，执行违规保留失败 case，decision_trace 保存 expected/actual/matched。pass 只由可信的 applicable+真实 passed 产生；跳过/未知没有运行，也不进入通过数。Demo 默认六行结果是 2 violation、2 pass、2 skipped，总共 4 次 Replay 执行，另有 capture/compile 的真实自检运行。

## 退出码与复验

| 码 | 语义 |
|---:|---|
| 0 | 该命令完成/验收成功；Replay 也可能是 skipped_inapplicable，Demo 仍有真实 violation |
| 1 | 确认违规，或 capture/evaluate/demo 验收未满足 |
| 2 | 参数/配置不合法（例如未知输出格式，在执行前拒绝） |
| 3 | 执行基础设施异常/timeout/不可用 IO |
| 4 | Replay unknown，或学习证据不足而拒绝 |
| 5 | 来源/摘要/已发布报告完整性失败 |

既有 audit/verify 命令的 0 仅表示审核成功，不替换原 verdict。`demo --verify-only` 同样只读，并保留原 accepted 的退出语义。格式切换不改变这些规则，不将 stderr 的配置/完整性错误包装为正常结果。

D12 修正了 compile 自检错误分支：旧实现调用 `_emit_run` 时，test_failed 会提前退出 1，使后面的预期退出 3 不可达。现在所有格式都先输出实际自检 Run，再退出 3；这是编译/固定目标自检失败，不是新目标的确认 violation。原直接 `guard run` 的真实断言失败仍退出 1。该兼容差异明确保留，未修改任何原执行记录。

标准 Demo 使用已录制请求和显式 pin 的可信本地源码/契约。它不访问网络，不依赖 API key，不使用仓库旧 artifacts、未记录的 pytest 插件或 conftest。pytest/Python/Pydantic/Typer 版本记录在 Pipeline 中；改变环境后使用新 workspace。任意仓库代码需要独立的隔离与准入，当前受限 Docker 接入见下文。

## fork MAC 试点专用入口

当前 `counterguard preflight` 的默认命令仍对应正式 v1 的 pytest8.4.2/root-imports，
不会因为安装了新镜像而自动放宽。pytest9/src 的受限试点使用显式冻结 manifest：

```powershell
uv run python scripts/run_pilot.py --manifest integrations/pilot/manifest-v5.yaml --phase preflight --output artifacts/pilot/validators-fork-v3/admission-new
uv run python scripts/run_pilot.py --manifest integrations/pilot/manifest-v5.yaml --phase replay --output artifacts/pilot/validators-fork-v3/replay-new
```

每个输出目录必须全新。`build-guard` 每个捕获版本只运行一次，不能重复覆盖工作区或旧产物；
已完成的 Guard 用 replay 重放。新版本仓库 Evidence/Guard 只能经这个 Docker 路径捕获/自检/执行，
不支持通过原 trusted-local compile/guard run 绕过审核。
配置 `counterguard.yaml` 仍是 **JSON 语法子集**，不是带缩进/注释的通用 YAML。

独立复核并比较两次真实重放：

```powershell
uv run python scripts/run_pilot.py --manifest integrations/pilot/manifest-v5.yaml --phase compare --first artifacts/pilot/validators-fork-v3/replay-1/report.json --second artifacts/pilot/validators-fork-v3/replay-2/report.json --output artifacts/pilot/validators-fork-v3/compare-new
```

本入口的失败退出 4，保存具体错误和 next_stage_allowed=false；没有本地回退。
unknown / disabled 只表示跳过，不能算 pass。完整规则、来源分类和恢复本地 owner 提交见
[试点设计](../integrations/pilot/design-fork-v1.md)。该入口不声明已经支持任意仓库、插件或作用域学习。
