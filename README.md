# CounterGuard

**面向 AI 生成代码的缺陷回归防线。**

CounterGuard 把**已验证的缺陷证据**转化为**可复用的回归守卫**，并为每条守卫给出**显式的适用边界**。

> 中文 · [English](README.en.md)

## 它解决什么问题

AI 生成和修改的代码有一个结构性缺口：**它不知道你三个月前修过什么**。同一个缺陷因此可能被反复引入，而"靠人记得"从来不是可靠的机制。

CounterGuard 让每一次修复都变成一条**永久检查**——而且这条检查**知道自己该在什么时候生效**。规则不是全局的：每条守卫的适用边界，是从**已确认的反例**里学出来的。

## 安装

```powershell
uv sync
uv run counterguard --help

uv build
python -m pip install "dist/counterguard-0.5.0-py3-none-any.whl[runner]"
```

wheel 提供 CLI 与库；**要执行测试需安装 `runner` extra**（它声明项目已使用的 pytest 依赖）。缺少 pytest 时，执行会在**创建任何输出之前**退出 `3`，并提示安装 `counterguard[runner]`。

离线 Demo 还需要源码分发包里的 `examples/`、`benchmarks/`、`experiments/` 与契约测试——**这些不打包进库 wheel**。

## 快速开始

```powershell
uv run counterguard demo --scenario examples/demo/mvp.yaml --workspace artifacts/quickstart-v1
```

一条命令从干净输入跑通全流程，并写出 `report.json` 与 `report.md`。重复执行只做只读审核与重新渲染。

```powershell
uv run counterguard demo --workspace artifacts/quickstart-v1 --format markdown
uv run counterguard demo --workspace artifacts/quickstart-v1 --verify-only
```

⚠️ **注意**：场景文件虽然叫 `mvp.yaml`，但**当前只支持 JSON 语法**（YAML 的缩进、注释、锚点均不支持）。[快速开始文档](docs/quickstart.md)里给了合法输入，以及一个真实的"缺少契约 → unknown"回放。

默认 Demo 使用**录制候选**与**可信本地 fixture**，不依赖网络与实时模型。**它不为任意 Python 提供沙箱。**

## 三个状态必须分开

这是整个项目的核心设计：**「适用性」「执行结果」「最终判定」是三个独立的量。**

| 维度 | 取值 |
|---|---|
| `scope_decision` | `applicable` / `inapplicable` / `unknown` |
| `execution_outcome` | `not_run` / `pass` / `fail` / `error` / `timeout` |
| `final_verdict` | `pass` / `violation` / `skipped` / `inconclusive` |

**不适用与信息不足都不启动 pytest**——输出 `not_run` + `skipped`；基础设施故障输出 `inconclusive`。**跳过的目标永远不会变成"通过"。**

报告同时给出最小失败用例、initial/refined 规则、逐条 clause 的比对结果与来源链接。详见 [CLI 契约](docs/cli.md)。

## 工作机制

四个步骤，每一步都产出带版本与摘要的产物：

1. **捕获**——只有「真实 buggy 失败 + 修复后通过」才算可复现 Evidence；契约/测试/目标摘要、结构化 case 结果与原始日志全部记录
2. **编译**——失败 case 变成独立的**最小 Guard**，并在 fixed 目标上自检后才发布
3. **学边界**——守卫的适用性从**已确认的反例**拟合而来。纯求解器只接受 `FeatureVector` + 严格适用性 bool；来源、身份字段与泄漏子类都会被拒绝
4. **重放**——**先判定适用性，再决定是否启动 pytest**；跳过的行保留 `run=null`

## 冻结基准

15 个有标注的场景：**9 个训练 + 6 个留出**。每条守卫在两个拆分里都有适用与不适用样本，且留出实现使用了训练中不存在的代码形态。

作用域特征**刻意排除**契约 ID、路径、模块名、目标名、期望输出与 oracle 值——规则不能靠"记住答案"工作。其中有一个**不适用但违反自身契约**的目标，证明**适用性无法从"目标是否正确"推断**。

### 会员折扣守卫

源契约：`membership_discount` 的 `v1` final-price。

- 会员按原价 80% 支付；非会员按原价支付
- 保留两位小数、**四舍五入（half-up）**；负数金额被拒绝

编译出的 Guard **只保留在源缺陷上失败的那两个会员价用例**。

### 查询上限校验守卫

源契约默认 20，只接受 1–100 的 ASCII 十进制数字串；带符号、补零、Unicode 数字、畸形与超范围输入一律拒绝。

编译出的 Guard **只保留"拒绝 0"这一条断言**。

## 作用域学习

```powershell
uv run counterguard scope learn --protocol experiments/scope_v1.json --phase initial --output artifacts/.../initial
uv run counterguard scope learn --protocol experiments/scope_v1.json --phase refined --output artifacts/.../refined
```

两个 **initial** 规则都学出 `contract_version == v1`；**加入两个冻结的合法反例后完整重训**，学出 **version AND interface** 规则（discount 为 `final_price`，input-limit 为 `query_parameter`）。

在全部 9 个训练行上：

| 阶段 | TP | FP | TN | FN |
|---|---:|---:|---:|---:|
| initial | 4 | 2 | 3 | 0 |
| **refined** | **4** | **0** | **5** | **0** |

搜索空间记录为 `predicate_count` / `combination_count`：discount **8/92**，input-limit **10/175**。输入随机打乱 20 次后，学出的规则与 digest 保持一致。**留出样本永不进入拟合。**

## 重放与评测

```powershell
uv run counterguard benchmark replay --protocol experiments/scope_v1.json --phase refined --split train
uv run counterguard experiment evaluate --protocol experiments/scope_v1.json --split holdout --fitted artifacts/experiments/scope-v1/fitted --output artifacts/experiments/scope-v1/final
```

训练重放预期退出码 `1`（因为有两条适用目标真的违反了守卫）：**2 通过、2 违规、5 跳过**，且**实际只启动 4 次 pytest 进程**。每一行跳过都是 `run=null`。

留出集上的四方法结果：

| 方法 | TP / FP / TN / FN | 错误应用率 | Bug Recall |
|---|---|---:|---:|
| always | 2 / 4 / 0 / 0 | 1.0 | 1/1 |
| fixed interface | 2 / 2 / 2 / 0 | 0.5 | 1/1 |
| learned initial | 2 / 2 / 2 / 0 | 0.5 | 1/1 |
| **learned refined** | **2 / 0 / 4 / 0** | **0.0** | **1/1** |

**refined 修正了 2 次错误应用、保留了 2 个适用样本、没有新增 FP/FN。** query 守卫没有留出缺陷，因此其 Bug Recall 报告为 `null`，而不是 100%。

冻结的混淆口径把 unknown 计为负预测，**同时单独报告其比率与决策覆盖率**；原始结果保留 unknown。

> `evaluate` 退出 0 表示**实验满足冻结验收**，不表示每条守卫都通过。这 6 个标签已经公开，所以这是**工程验证，不是盲测**。

`replay verify` 在不执行 pytest 的前提下审核当前输入。**审核成功只表示记录完整，不表示记录的 verdict 是 pass。**

## CLI 与退出码

`capture`、`compile`、`learn`、`replay run`、`evaluate` 都支持 `--format text|json|markdown`。显式格式把原始 payload 包装进 `command-report.v1`；不传 `--format` 时保留原有 JSON 形状。**格式化不改变退出码。**

| 码 | 含义 |
|---|---|
| `0` | 可复现 Evidence / 验收通过 |
| `1` | 已完成但未复现；或适用守卫确认违规 |
| `2` | 输入非法 |
| `3` | 执行故障（含缺 pytest 元数据） |
| `4` | 信息不足（unknown）；或学习拒绝泛化 |
| `5` | 产物完整性失败 |

pytest 自身的 2–5、缺失或歧义的 case 结果、超时——**都不能算作可复现缺陷**。

## 开发

源码版提供 [统一仓库验证](docs/verify.md) 和 [追加式 Guard 生命周期](docs/guard-lifecycle.md)。`verify` 在 Docker 中重放已审核的 Shadow/Active Guard，分别报告 unknown、跳过和执行异常。支持根布局已知源码快照及固定 validators 的 src/pytest9 profile；`counterguard runner list` 可查审核镜像与来源，再用 `--runner-id` 选择。其他项目先满足 [接入条件](docs/project-admission.md)。

[首次接入清单](docs/onboarding.md)明确材料、责任和初始 Scope；新项目可以先用 `preflight --profile minimal-python --import-root src` 做只读分类，尚不自动获准执行。[CI 示例与 Summary](docs/github-actions.md)当前仅覆盖工具自带可信 fixture，未宣称任意项目或真实 GitHub 平台已验收。

已有回归测试可用 [contract draft](docs/contract-drafts.md)机械起草受限契约提案，逐项保留不支持的断言；提案不可执行，仍需人审。[实际试走](docs/results/onboarding-boltons-v1/README.md)和[接入路线](docs/roadmap.md)分别记录遇阻数据与尚缺能力。

[bootstrap plan](docs/bootstrap-plans.md)进一步分列目标导入闭包与上游测试环境，保留完整提交来源；计划不授予执行权限。零运行时依赖不代表无需 fixture、hook 或测试插件。

[contract prepare / bootstrap bind](docs/standalone-contracts.md)支持 H 内受限通用契约和 B/F 来源重建；所有者须审核并提交。
之后可在已审核 Docker 中[双向捕获](docs/standalone-capture.md)，再[编译最小 Guard、审核快照 Scope 并进入 Shadow](docs/standalone-guards.md)。
只支持受限独立字面量契约；新源码仍 unknown，不安装依赖、不加载原生 pytest 引导、不自动提升 Active。

```powershell
uv run pytest -m "not slow" -q      # 快速层：不启动真实子进程
uv run ruff check .
uv run pytest -q --durations=20      # 完整套件，交付前跑一次
```

集成/e2e 测试、重型 fixture 与真实子进程标记为 `slow`。**快测会在 fixture 准备、执行与清理阶段拒绝未标记的真实进程启动**——因此任何会起进程的新测试都必须声明自己是 `slow`。详见 [testing.md](docs/testing.md)。

## 项目结构

```text
src/counterguard/     实现与 CLI
tests/                单元、集成与端到端测试
schemas/              每个产物的 JSON Schema
benchmarks/           冻结的标注样本、拆分与模块上下文
examples/             Demo 场景、契约与实现
experiments/          冻结的实验协议
containers/           受限 Docker 执行器
docs/                 架构、数据契约、CLI、安全模型、已知限制
```

运行期产物 `artifacts/` 与发行物 `dist/` 已排除出 Git。

## 安全与限制

因为 CounterGuard 会**执行代码**并**读取仓库**，它自身的安全姿态很重要：

- **[docs/security-model.md](docs/security-model.md)**——资产、信任假设，以及仓库检查与容器执行的具体控制
- **[docs/attack-surface-checklist.md](docs/attack-surface-checklist.md)**——逐项列出「已测 / 部分覆盖 / **完全未覆盖**」
- **[docs/known-limitations.md](docs/known-limitations.md)**——当前范围声明与历史验证边界

已记录的验证使用本地 Python 工具和固定 Linux Docker 镜像。不把这些记录扩展为跨平台矩阵、任意恶意仓库隔离、签名认证或程序等价性证明。

## 许可

[Apache-2.0](LICENSE)
