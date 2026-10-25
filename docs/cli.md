# CLI 与报告约定

这一页列出命令、输出格式、退出码，以及几个容易混淆的状态。字段级契约在 `schemas/`，各命令的来源与安全边界见对应的说明页。

## 命令一览

| 命令 | 用途 | 细节 |
|---|---|---|
| `demo` | 离线 Demo | [快速开始](quickstart.md) |
| `capture` / `compile` / `learn` / `replay run` / `evaluate` | 主链路 | 本页「命令与兼容」 |
| `preflight` | 只读预检 | [预检](preflight.md) |
| `inspect` | 只读仓库检查 | [仓库检查](repository-inspection.md) |
| `contract draft` | 从已有测试生成草案 | [测试转草案](contract-drafts.md) |
| `contract prepare` · `bootstrap bind` / `verify-binding` | H 内契约与 B/F 来源绑定 | [来源绑定](standalone-contracts.md) |
| `bootstrap plan` | 输入计划，不可执行 | [输入计划](bootstrap-plans.md) |
| `bootstrap capture` / `verify-evidence` | Docker 双向捕获 | [捕获](standalone-capture.md) |
| `bootstrap compile` / `verify-guard` | 最小编译与自检 | [独立 Guard](standalone-guards.md) |
| `registry add/list/show/disable` | 本地 Registry | [Registry](registry.md) |
| `runner list/show` | 已审核镜像 | [runner 发现](runners.md) |
| `verify` | 统一验证 | [verify](verify.md) |
| `guard transition/history` | 生命周期 | [生命周期](guard-lifecycle.md) |
| `research-snapshot ...` | 工具自有快照接口 | [研究快照](research-snapshots.md) |
| `ci-report` | 受限 CI Summary | [CI](github-actions.md) |

报告格式为 `command-report.v1` 和 `demo-report.v1`。命令格式化不会修改冻结 scope_v1 的标签、标准、公式或已发布记录。

## 接入命令速查

- **契约与来源绑定**：`contract prepare` 返回 4，需要人工审核；所有者提交后，`bootstrap bind` 与 `bootstrap verify-binding` 重建 B/F/H。返回 0 只表示来源事实已核对、静态输入待审；unknown 或 blocked 返回 4，完整性拒绝返回 5。这些命令不生成 Evidence，也不给执行授权。
- **Docker 双向捕获**：`bootstrap capture --repo ... --binding ... --runner-id ... --evidence-id ... --review-reason ... --output ...`；`bootstrap verify-evidence <evidence.json> --repo ...` 只读重建来源、授权和日志，不启动 Docker。复现返回 0、有效测试未复现 1、执行故障 3、输入未就绪 4、完整性拒绝 5。只用已审核的 root-pytest8 镜像，不回退本地。
- **最小 Guard**：`bootstrap compile ...` 和 `bootstrap verify-guard ...`；登记用 `registry add ... --repo ...`。来源和真实自检都通过才生成 Candidate，人工审核进入 Shadow 后才能走统一 verify。
- **输入计划**：`bootstrap plan` 读取提交树，列出目标导入闭包、草案覆盖和全仓引导需求。它始终不可执行、返回 4，不是 verify 或契约批准入口。
- **只读预检**：`preflight --repo <repo> --revision <sha>` 覆盖完整提交树和新旧 pytest TOML 配置，不 import、不安装仓库。0 只表示静态候选，blocked 或 unknown 返回 4、拒绝返回 5，`execution_allowed` 始终为 false。
- **统一 verify**：`runner list/show` 只读展示审核来源和本机可用性；`verify --runner-id ...` 只用 Docker。报告为 `verify-report.v2`，旧的 v1 和 `command-report.v1` 保留原契约。
- **本地 Registry**：`registry add/list/show/disable`。来源完整性失败退出 5，禁用是追加终态，不提升 Guard 生命周期。

### 静态重导出 v2 profile

多项静态根导出和有限类查找钩子使用显式的 v2 profile：

```powershell
counterguard bootstrap inspect-target --repo <repo> --revision <sha> --target package:public --import-root . --profile static-reexport-v2 --output <new-inspection>
counterguard contract prepare --repo <repo> --buggy <B> --fixed <F> --contract-id <new-id> --target package:public --import-root . --test-ref <test.py> --test-function <test_name> --profile static-reexport-v2 --output <new-preparation>
```

`inspect-target` 读完整提交树，但不要求比较目标提供虚构的 B/F/H 或契约，始终 not_run、退出 4。源码来源的 `prepare` 仍然要求真实修复和测试，生成 contract.v6，所有者 H 和另行审核都不能省。省略 `--profile` 时，`prepare` 和 `plan` 使用 `existing`，v3/v4/v5 的接受范围不变；未知 profile 不会回退成可执行格式。静态的 `review_required` 不代表已授权或测试通过。

## 仓库检查 `inspect`

源码开发版提供 `inspect --repo ... --base ... --head ... --config ... --format json|text|markdown`，使用独立的 `repository-inspection.v1`，不扩展旧 `command-report.v1`，也不把候选影响当成 Replay verdict。完整可运行示例见[只读仓库检查](repository-inspection.md)，安全准入见[安全模型](security-model.md)。

配置是严格 JSON 子集，即使扩展名是 `.yaml`。ready / unknown / rejected 分别退出 0 / 4 / 5；无效配置或修订语法退出 2。三种格式同源，unknown 和拒绝都会保留原因。所有结果都是 `execution_allowed=false` / not_run，不能由 ready 推断可执行或测试通过。冻结的 v0.1.0 wheel 不包含这个后续源码功能。

## 场景文件格式

`mvp.yaml` 当前只能写 JSON 语法，不支持通用 YAML。`.yaml` 后缀不会启用缩进映射、注释或锚点，请用双引号、花括号和方括号，不加尾逗号。解析器复用现有的 Pydantic JSON 入口，不引入 YAML 依赖。完整可用的内容和会被拒绝的 YAML 反例见[快速开始](quickstart.md)；语法不支持返回 2，并在执行前拒绝。

标准 Demo 选择的六个冻结训练样本信息完整，所以原报告没有 unknown。单独用缺少 `--contract` 的真实 Replay 演示 unknown 的用法见[快速开始](quickstart.md#结果怎么读)。这条路径必须保留 unknown / not_run / skipped 和退出 4，不改动标准六行或评测分母。

## 命令与兼容

| 入口 | 原入口 / 含义 | 输出 |
|---|---|---|
| capture | 直接双向捕获，或 `--request` 加 recorded Gate | 未指定 `--format` 时保持原 Evidence / Gate JSON |
| compile | 最小 Guard 编译与 fixed 自检 | 未指定时保持原 Guard JSON |
| learn | `scope learn` 的同函数别名，只跑 train | 未指定时保持原 FitManifest JSON |
| replay run | 带 Scope 的真实重放；`replay verify` 保持只读审核 | run 支持格式选项；未指定时保持 ReplayResult JSON |
| evaluate | `experiment evaluate` 的同函数别名，只跑 holdout | 未指定时保持原 EvaluationReport JSON |
| demo | 离线 recorded Pipeline 加已验证事实报告 | 默认 text；同时持久化 JSON 和 Markdown，三格式同源 |

上表的执行入口都支持 `--format text|json|markdown`。显式格式统一包成 CommandReport：operation、原始 payload、规范化 replays。原 artifact 的自摘要仍然在 payload 里，包装后的完整 JSON 不能当作 Evidence / Guard / ReplayResult 的原 schema 加载。Demo 的完整 JSON 是 DemoReport，内含同一个 CommandReport、真实创建时间、Pipeline 链接、展示代码摘要和自摘要，对应 `schemas/demo-report.schema.json`。

capture、compile、learn、evaluate 不是「新目标是否通过」的单行 Replay：它们的 replays 为空，不会给出虚构的 `scope_decision`。evaluate 的四方法事实、指标和 Markdown 仍由 evaluation 的不可变结果文件提供；CLI 格式选项只展示原 EvaluationReport，不把验收摘要冒充逐行执行。

```powershell
uv run counterguard learn --protocol experiments/scope_v1.json --phase refined --output artifacts/fitted-new/refined --format markdown
uv run counterguard replay run --guard <guard.json> --scope <scope.json> --target <module:symbol> --contract <contract.json> --format json
uv run counterguard demo --scenario examples/demo/mvp.yaml --workspace artifacts/cli-demo-v1
uv run counterguard demo --workspace artifacts/cli-demo-v1 --format json
uv run counterguard demo --workspace artifacts/cli-demo-v1 --format markdown
uv run counterguard demo --workspace artifacts/cli-demo-v1 --verify-only
```

尖括号路径要换成同一来源链里的实际资产，不要混用旧 Guard 和新 fit 的摘要。已有失败、部分完成的目录，或代码与输入已经变化时，换一个新的 workspace 版本，不要删除或重签原产物来「恢复」。

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

`raw_outcome` 和 `raw_verdict` 不会丢；unknown 保留具体原因，执行违规保留失败 case，`decision_trace` 保存 expected / actual / matched。pass 只能由可信的 applicable 加真实 passed 产生；跳过和未知没有运行，也不进入通过数。Demo 默认六行的结果是 2 violation、2 pass、2 skipped，总共 4 次 Replay 执行，另外还有 capture / compile 的真实自检运行。

## 退出码与复验

| 码 | 语义 |
|---:|---|
| 0 | 命令完成或验收成功；Replay 也可能是 skipped_inapplicable，Demo 仍会带真实 violation |
| 1 | 确认违规，或 capture / evaluate / demo 的验收未满足 |
| 2 | 参数或配置不合法，例如未知输出格式，在执行前拒绝 |
| 3 | 执行基础设施异常、timeout 或不可用 IO |
| 4 | Replay unknown，或学习证据不足而拒绝 |
| 5 | 来源、摘要或已发布报告的完整性失败 |

既有 audit / verify 命令的 0 只表示审核成功，不替换原 verdict；`demo --verify-only` 同样只读，并保留原 accepted 的退出语义。格式切换不改变这些规则，也不会把 stderr 的配置或完整性错误包装成正常结果。

compile 自检失败时，CLI 会先输出实际 Run，再以 3 退出。这是编译或固定目标自检失败，不是新目标的确认 violation；直接 `guard run` 的真实断言失败仍然以 1 退出。

标准 Demo 使用已录制的请求和显式 pin 的可信本地源码与契约。它不访问网络，不依赖 API key，也不使用仓库旧 artifacts、未记录的 pytest 插件或 conftest。pytest、Python、Pydantic、Typer 的版本记录在 Pipeline 里；改变环境后用新的 workspace。任意仓库代码需要独立的隔离与准入，受限 Docker 接入见下文。

## 新项目分类与 CI 输出

```powershell
counterguard contract draft --repo <repo> --revision <sha> --test-ref tests/test_price.py --test-function test_price --target package.pricing:price --output artifacts/proposals/new-id
```

这条命令不执行目标。draft_ready / 0 只代表语法投影完整；partial 或 unsupported / 4 会保留未支持项，并先写出草案。用户必须审核，草案不能进 Registry 或 verify。完整语法和来源边界见[测试转草案](contract-drafts.md)。

```powershell
counterguard preflight --repo <repo> --revision <full-sha> --profile minimal-python --import-root src
counterguard runner list
counterguard ci-report --report <verify-output>/report.json --output <new-public-output>
```

新 profile 只做静态候选分类，不给执行授权。findings 指向三种前置：导入、pytest 引导、安装；第四种（通用仓库 Guard 与 bootstrap）仍需实现和审核。人工责任见[首次接入](onboarding.md)。v2 另带 `user_guidance` / `next_step`，直接告诉用户先做什么；工程编号只给维护者，不能靠配置打开未实现的能力。runner 发现会逐项核对包内的构建与攻击收据，再探测精确 image ID，损坏时退出 5。CI 输出保留 verify 的退出码，只导出受限公开字段，详见 [CI](github-actions.md)。

## fork MAC 试点专用入口

`counterguard preflight` 的默认命令对应正式 v1 的 pytest 8.4.2 / root-imports，不会因为装了新镜像就自动放宽。pytest9 / src 的受限试点使用显式冻结 manifest：

```powershell
uv run python scripts/run_pilot.py --manifest integrations/pilot/manifest-v5.yaml --phase preflight --output artifacts/pilot/validators-fork-v3/admission-new
uv run python scripts/run_pilot.py --manifest integrations/pilot/manifest-v5.yaml --phase replay --output artifacts/pilot/validators-fork-v3/replay-new
```

每个输出目录必须是全新的。`build-guard` 对每个捕获版本只运行一次，不能重复覆盖工作区或旧产物；已经完成的 Guard 用 replay 重放。新版本仓库的 Evidence / Guard 只能经这条 Docker 路径捕获、自检和执行，不能用原来的 trusted-local compile / guard run 绕过审核。`counterguard.yaml` 同样是 JSON 语法子集，不是带缩进和注释的通用 YAML。

独立复核并比较两次真实重放：

```powershell
uv run python scripts/run_pilot.py --manifest integrations/pilot/manifest-v5.yaml --phase compare --first artifacts/pilot/validators-fork-v3/replay-1/report.json --second artifacts/pilot/validators-fork-v3/replay-2/report.json --output artifacts/pilot/validators-fork-v3/compare-new
```

这个入口失败时退出 4，保存具体错误和 `next_stage_allowed=false`，没有本地回退。unknown 或 disabled 只表示跳过，不能算 pass。完整规则、来源分类和恢复本地 owner 提交见[试点设计](../integrations/pilot/design-fork-v1.md)。该入口不声明已经支持任意仓库、插件或作用域学习。

## 工具自有研究快照

`counterguard research-snapshot --help` 提供独立的 prepare / bind / review / capture / compile / replay / audit。完整契约、容量、独立审核锚和用途限制见[研究快照](research-snapshots.md)。这个入口只验证工具自有 fixture，不是任意项目的 `verify`，也不是生产 Shadow 接入，不批准外部数据执行。

另有 `counterguard research-snapshot comparison --help`，提供完整目标检查、全最小 case 的原样映射、独立比较审核、Docker run / audit-only 和只读 verify。目标自身的 oracle 独立；learned 在这个新 profile 尚无 fit 时为 unknown。用途和退出语义见[独立比较](snapshot-comparisons.md)。
