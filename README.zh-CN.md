# CounterGuard

**面向 AI 生成代码的缺陷回归防线。**

CounterGuard 把**已验证的缺陷证据**转化为**可复用的回归守卫**，并为每条守卫给出**显式的适用边界**。

> [English](README.md) · 中文

## 它解决什么问题

AI 生成和修改的代码有一个结构性缺口：**它不知道你三个月前修过什么**。同一个缺陷因此可能被反复引入，而"靠人记得"从来不是可靠的机制。

CounterGuard 的做法是：**把每一次修复变成一条永久检查**，并且这条检查**知道自己该在什么时候生效**——不是全局规则，而是从真实反例里学出的边界。

## MVP 0.1.0 覆盖范围

可信的本地 Python / pytest 流水线：

- **双向 Evidence**：只接受「真实 buggy 失败 + 修复后通过」作为可复现证据
- **最小 Guard 编译**：只保留实际失败的那几条断言，并在 fixed 目标上自检
- **initial / refined 作用域学习**：加入已确认的合法反例后完整重训
- **Scope-aware Replay**：先判定适用性，再决定是否启动 pytest
- **离线 Demo**：一条命令跑通全流程

延伸阅读：[架构](docs/architecture.md) · [冻结评测](docs/evaluation.md) · [发布与安装](docs/release.md) · [攻击面清单](docs/attack-surface-checklist.md) · [已知限制](docs/known-limitations.md)（含[历史验证结论的边界](docs/known-limitations.md#历史验证结论的边界)）

## 快速开始

```powershell
uv sync
uv run counterguard demo --scenario examples/demo/mvp.yaml --workspace artifacts/quickstart-v1
```

Demo 会在工作区生成 `report.json` 与 `report.md`。重复执行只做只读审核与渲染。

⚠️ **注意**：场景文件虽然叫 `mvp.yaml`，但**当前只支持 JSON 语法**（YAML 的缩进、注释、锚点均不支持）。[快速开始](docs/quickstart.md)里给了合法输入示例，以及一个真实的「缺少契约 → unknown」回放。

**安装方式**：

- wheel 提供 CLI 与库；**要执行测试需安装 `runner` extra**（它声明项目已使用的 pytest 依赖）
- 离线 Demo 还需要源码分发包里的 `examples/`、`benchmarks/`、`experiments/` 与契约测试——**这些不打包进库 wheel**
- 缺少 pytest 时，执行会在创建任何输出**之前**退出 3，并提示安装 `counterguard[runner]`

## 报告输出的三态分离

这是整个项目的核心设计：**「适用性」「执行结果」「最终判定」是三个独立的量**。

| 维度 | 取值 |
|---|---|
| `scope_decision` | `applicable` / `inapplicable` / `unknown` |
| `execution_outcome` | `not_run` / `pass` / `fail` / `error` / `timeout` |
| `final_verdict` | `pass` / `violation` / `skipped` / `inconclusive` |

**不适用与信息不足都不启动 pytest**，输出 `not_run` + `skipped`；基础设施故障输出 `inconclusive`。**跳过永远不会变成"通过"。**

报告同时给出最小失败用例、initial/refined 规则、逐条 clause 的实际比对结果，以及来源链接。

默认 Demo 使用**录制候选**与**可信本地 fixture**，不依赖网络与实时模型；**它不为任意 Python 提供沙箱**。

## 命令行

`capture`、`compile`、`learn`（`scope learn` 的别名）、`replay run`、`evaluate`（`experiment evaluate` 的别名）都支持 `--format text|json|markdown`。

显式格式使用 `command-report.v1`：`payload` 保留原始产物，`replays` 在适用时包含规范化的执行结论。不传 `--format` 时保留原有 JSON 形状（Demo 默认 text）。**格式化不改变退出码。**

完整选项、状态映射与审计命令见 [CLI 契约](docs/cli.md)。

### 退出码

| 码 | 含义 |
|---|---|
| `0` | 可复现 Evidence / 验收通过 |
| `1` | 已完成但未复现；或适用 Guard 确认违规 |
| `2` | 输入非法 |
| `3` | 执行故障（含缺 pytest 元数据） |
| `4` | 信息不足（unknown）；或学习拒绝泛化 |
| `5` | 产物完整性失败 |

pytest 自身的 2–5、缺失或歧义的 case 结果、超时**都不能算作可复现缺陷**。未能复现时保留诊断 Evidence。

## 冻结基准（Day 2）

15 个有标注的场景：**9 个训练 + 6 个留出**。每条 Guard 在两个拆分里都有适用与不适用样本；留出实现使用了训练中不存在的代码形态。

作用域特征**刻意排除**了契约 ID、路径、模块名、目标名、期望输出与 oracle 值——即规则不能靠"记住答案"来工作。

字段边界与标签语义见 `benchmarks/README.md`。其中有一个**不适用但违反自身契约**的目标——它证明**适用性不能从"目标是否正确"推断出来**。

### 会员折扣守卫

源契约为 `membership_discount` 的 `v1` final-price：

- 会员按原价 80% 支付
- 非会员按原价支付
- 结果保留两位小数、**四舍五入（half-up）**
- 负数金额被拒绝

编译出的 Guard **只保留在源缺陷上失败的那两个会员价用例**。

### 查询上限校验守卫

源契约默认 20，只接受 1–100 的 ASCII 十进制数字串，拒绝带符号、补零、Unicode 数字、畸形与超范围输入。

编译出的 Guard **只保留"拒绝 0"这一条回归断言**。

两个 Guard 都有可复现的失败演示：

```powershell
$env:COUNTERGUARD_TARGET = "examples.discount.implementations.final_price_v1_buggy"
uv run pytest tests/contract_tests/test_membership_discount_v1.py
Remove-Item Env:COUNTERGUARD_TARGET
```

## 作用域学习

```powershell
uv run python scripts/prepare_scope_v1.py
uv run counterguard scope learn --protocol experiments/scope_v1.json --phase initial --output artifacts/experiments/scope-v1/fitted/learning-v2/initial
uv run counterguard scope learn --protocol experiments/scope_v1.json --phase refined --output artifacts/experiments/scope-v1/fitted/learning-v2/refined
```

**结果**：两个 initial 规则都学出 `contract_version == v1`；**加入两个冻结的合法反例后完整重训**，学出 version AND interface 规则（discount 为 `final_price`，input-limit 为 `query_parameter`）。

在全部 9 个训练行上：

| 阶段 | TP | FP | TN | FN |
|---|---:|---:|---:|---:|
| initial | 4 | 2 | 3 | 0 |
| **refined** | **4** | **0** | **5** | **0** |

**纯求解器只接受精确的 `TrainingExample`**（一个 `FeatureVector` + 严格的适用性 bool）；`FeatureRecord`、来源字典、身份字段与泄漏子类都会被拒绝。**留出样本永不进入拟合。**

搜索空间记录为 `predicate_count` / `combination_count`：discount 为 **8 / 92**，input-limit 为 **10 / 175**。

学习输入随机打乱 20 次后，结果与 digest 保持一致。拒绝泛化退出 4，schema/类型错误退出 2，产物错误退出 5。详见 [Day 7 记录](docs/progress/day7.md)。

## Scope-aware 重放

```powershell
uv run counterguard benchmark replay --protocol experiments/scope_v1.json --phase refined --split train
```

预期退出码是 **1**（因为有两条适用目标真的违反了 Guard）。报告先写出：**2 通过、2 违规、5 不适用跳过**，且**实际只启动 4 次 pytest 进程**。

每一行跳过都是 `run=null`；unknown 使用 `skipped_unknown`，**永不写成 inapplicable 或 pass**。

> `replay verify` 在不执行 pytest 的前提下审核当前输入。**审核成功只表示记录完整，不表示记录的 verdict 是 pass。**

## 留出集上的四方法评测

```powershell
uv run counterguard experiment evaluate --protocol experiments/scope_v1.json --split holdout --fitted artifacts/experiments/scope-v1/fitted --output artifacts/experiments/scope-v1/final
uv run counterguard experiment verify --run artifacts/experiments/scope-v1/final
```

| 方法 | TP / FP / TN / FN | FAR | Bug Recall |
|---|---|---|---|
| B1 always | 2 / 4 / 0 / 0 | 1.0 | 1/1 |
| B2 interface | 2 / 2 / 2 / 0 | 0.5 | 1/1 |
| learned initial | 2 / 2 / 2 / 0 | 0.5 | 1/1 |
| **learned refined** | **2 / 0 / 4 / 0** | **0.0** | **1/1** |

**refined 修正了 2 次错误应用，保留了 2 个适用样本，没有新增 FP/FN。** query Guard 没有留出缺陷，因此它的 Bug recall 报告为 `null`（而不是 100%）。

冻结的混淆口径把 unknown 计为负预测，**同时单独报告其比率与决策覆盖率**；原始结果保留 unknown。

> `evaluate` 退出 0 表示**实验满足冻结验收**，不表示每条 Guard 都通过。
> 这 6 个标签已经公开，所以这是**工程验证，不是盲测**。

## 开发检查

```powershell
uv sync
uv run pytest -m "not slow" -q      # 日常快测（秒级）
uv run ruff check .
```

交付前跑一次完整套件：

```powershell
uv run pytest -q --durations=20
```

**测试分层**：不筛选的命令仍然运行全部测试。集成/e2e、重型 fixture 与真实子进程标记为 `slow`。**快测会在 fixture 准备、执行与清理阶段拒绝真实进程启动**——这强制每条新测试必须正确声明自己属于哪一档。分层定义与耗时证据见 [testing.md](docs/testing.md)。

## 开发轨迹

| 阶段 | 内容 |
|---|---|
| Day 3 | 捕获并验证双向缺陷 Evidence（契约/测试/目标摘要、结构化 case、原始日志、pytest 退出语义） |
| Day 4 | 把失败 case 编译为独立 Guard 产物，并在 fixed 目标上自检后才发布 |
| Day 5 | 冻结实验协议、生成基线作用域、在 9 个训练行上执行两个基线 |
| Day 6 | 不执行目标即提取 AST 特征，并对账全部 15 个冻结标注 |
| Day 7 | 用冻结训练阶段 + 独立审计的模块上下文，拟合 initial / refined 作用域 |
| Day 8 | 验证捆绑并**自动判定适用性后才启动 pytest** |
| Day 9 | 在不重拟合的前提下，对留出集评测四种冻结方法 |
| Day 10 | 加入离线独立候选边界：录制提议引用权威契约 case，可信代码渲染测试，Verification Gate 只放行真实失败 |
| Day 11 | 在独立固定工作区里从干净输入跑通全流程（Pipeline） |
| Day 12 | 一键离线 Demo，并从同一份 JSON 事实渲染三种格式 |
| W3-A | 只读仓库检查：显式文件/契约映射，报告 affected / unaffected / unknown，**永不许可执行** |
| W3-B | Docker 受限执行器：非 root、只读根、禁网、资源与日志上限、子孙进程清理 |
| W3-D | 真实仓库试点（validators fork）：真实 buggy 10 个 case 失败 2 个、fixed 全部通过 |

每日验收记录在 [`docs/progress/`](docs/progress/)。运行期产物 `artifacts/` 已排除出 Git。

## 许可

[Apache-2.0](LICENSE)
