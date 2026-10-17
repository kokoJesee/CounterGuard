# CounterGuard

**让修过的缺陷，不再回来。**

AI 改代码的时候，不知道你三个月前修过什么。所以同一个 bug，会被它一而再地改回来。

CounterGuard 的做法很简单：每修好一个 bug，就把它记成一条检查。这条检查只在真的会踩到它的地方生效，其他地方不打扰你。

> 中文 · [English](README.en.md)

当前公开版本是 **[v0.5.0 Beta](https://github.com/kokoJesee/CounterGuard/releases/tag/v0.5.0)**。
[GitHub Release](https://github.com/kokoJesee/CounterGuard/releases/tag/v0.5.0) 里可以拿到 wheel、源码包、依赖清单、已审核的 runner 镜像和校验和。安装方式见 [Beta 说明](docs/beta-release.md)。还没上 PyPI。

## 安装

```powershell
uv sync
uv run counterguard --help

uv build
python -m pip install "dist/counterguard-0.5.0-py3-none-any.whl[runner]"
```

wheel 带 CLI 和库。**要真正跑测试，得装 `runner` 这个 extra**（它会带上 pytest）。没装 pytest 时，命令会在写任何东西之前退出 `3`，并提示你装 `counterguard[runner]`。

离线 Demo 还需要源码包里的 `examples/`、`benchmarks/`、`experiments/` 和契约测试——**这些不进 wheel**。

## 快速开始

```powershell
uv run counterguard demo --scenario examples/demo/mvp.yaml --workspace artifacts/quickstart-v1
```

一条命令从零跑完全流程，写出 `report.json` 和 `report.md`。再跑一遍只做只读校验、重新渲染。

⚠️ 注意：场景文件虽然叫 `mvp.yaml`，但**现在只认 JSON 语法**（YAML 的缩进、注释、锚点都不支持）。[快速开始](docs/quickstart.md) 里给了合法输入，还有一个真实的「缺契约 → unknown」例子。

默认 Demo 用录好的候选和可信本地 fixture，不需要联网、不需要模型。**它不是给任意 Python 用的沙箱。**

## 三种结果，分得清清楚楚

这是整个项目最重要的设计：**「该不该跑」「跑的结果」「最终结论」是三个独立的东西。**

| 维度 | 取值 |
|---|---|
| `scope_decision` | `applicable` / `inapplicable` / `unknown` |
| `execution_outcome` | `not_run` / `pass` / `fail` / `error` / `timeout` |
| `final_verdict` | `pass` / `violation` / `skipped` / `inconclusive` |

**不适用、信息不足，都不会启动 pytest**——结果是 `not_run` + `skipped`；环境故障是 `inconclusive`。**跳过的，永远不会被当成"通过"。**

报告里还有最小失败用例、initial/refined 规则、逐条 clause 的比对结果和来源链接。详见 [CLI 契约](docs/cli.md)。

## 工作机制

四步，每步留下可追溯的记录：

1. **捕获**——只有「buggy 真失败 + fixed 真通过」才算数；契约、测试、目标摘要、case 结果、原始日志全记下来
2. **编译**——把失败的 case 变成最小的 Guard，先在 fixed 目标上自检通过才发布
3. **学边界**——Guard 该在哪生效，靠**已确认的反例**学出来。求解器只吃 `FeatureVector` + 一个明确的适用性布尔值，来源、身份字段、会泄漏的东西一律拒绝
4. **重放**——**先判适用性，再决定跑不跑 pytest**；跳过的行留 `run=null`

## 冻结基准

15 个带标注的场景：**9 个训练 + 6 个留出**。每条 Guard 在两组里都有「适用」和「不适用」的样本，留出的实现用了训练里没出现过的代码形态。

作用域特征**故意排除**契约 ID、路径、模块名、目标名、期望输出和 oracle 值——规则不能靠"背答案"工作。里面还有一个「不适用但违反自己契约」的目标，证明**"该不该管"和"对不对"是两回事**。

### 会员折扣守卫

源契约：`membership_discount` 的 `v1` final-price。

- 会员付原价 80%；非会员付原价
- 保留两位小数、**四舍五入（half-up）**；负数金额拒绝

编译出的 Guard **只留源缺陷上失败的那两个会员价 case**。

### 查询上限校验守卫

源契约默认 20，只接受 1–100 的 ASCII 十进制数字串；带符号、补零、Unicode 数字、畸形、超范围全拒绝。

编译出的 Guard **只留"拒绝 0"这一条断言**。

## 作用域学习

```powershell
uv run counterguard scope learn --protocol experiments/scope_v1.json --phase initial --output artifacts/.../initial
uv run counterguard scope learn --protocol experiments/scope_v1.json --phase refined --output artifacts/.../refined
```

两个 **initial** 规则都学出 `contract_version == v1`；**加入两个冻结的合法反例再重训**，学出 **version AND interface**（discount 是 `final_price`，input-limit 是 `query_parameter`）。

9 个训练行上：

| 阶段 | TP | FP | TN | FN |
|---|---:|---:|---:|---:|
| initial | 4 | 2 | 3 | 0 |
| **refined** | **4** | **0** | **5** | **0** |

搜索空间记作 `predicate_count` / `combination_count`：discount **8/92**，input-limit **10/175**。输入随机打乱 20 次，规则和 digest 不变。**留出样本永远不进拟合。**

## 重放与评测

```powershell
uv run counterguard benchmark replay --protocol experiments/scope_v1.json --phase refined --split train
uv run counterguard experiment evaluate --protocol experiments/scope_v1.json --split holdout --fitted artifacts/experiments/scope-v1/fitted --output artifacts/experiments/scope-v1/final
```

训练重放预期退出 `1`（有两条适用目标真的违反了 Guard）：**2 通过、2 违规、5 跳过**，只启动 **4 次 pytest**。每一行跳过都是 `run=null`。

留出集上的四方法结果：

| 方法 | TP / FP / TN / FN | 错误应用率 | Bug Recall |
|---|---|---:|---:|
| always | 2 / 4 / 0 / 0 | 1.0 | 1/1 |
| fixed interface | 2 / 2 / 2 / 0 | 0.5 | 1/1 |
| learned initial | 2 / 2 / 2 / 0 | 0.5 | 1/1 |
| **learned refined** | **2 / 0 / 4 / 0** | **0.0** | **1/1** |

**refined 改掉了 2 次错误应用，保留了 2 个适用样本，没新增 FP/FN。** query 守卫没有留出缺陷，所以它的 Bug Recall 报 `null`，而不是 100%。

冻结口径把 unknown 当负预测，**同时单独报它的比率和决策覆盖率**；原始结果保留 unknown。

> `evaluate` 退出 0 表示**实验达到冻结验收标准**，不是每条 Guard 都过。这 6 个标签已经公开，所以这是**工程验证，不是盲测**。

`replay verify` 不跑 pytest，只审当前输入。**审核通过只说明记录完整，不说明当时的结论是 pass。**

## CLI 与退出码

`capture`、`compile`、`learn`、`replay run`、`evaluate` 都支持 `--format text|json|markdown`。显式格式会把原始 payload 包进 `command-report.v1`；不传 `--format` 就保留原来的 JSON。**格式化不影响退出码。**

| 码 | 含义 |
|---|---|
| `0` | 可复现 Evidence / 验收通过 |
| `1` | 做完了但没复现；或适用 Guard 确认违规 |
| `2` | 输入非法 |
| `3` | 执行故障（含缺 pytest 元数据） |
| `4` | 信息不足（unknown）；或学习拒绝泛化 |
| `5` | 产物完整性失败 |

pytest 自己的 2–5、缺失或歧义的 case、超时——**都不能算"可复现缺陷"**。

## 更多文档

- [统一仓库验证 `verify`](docs/verify.md) · [Guard 生命周期](docs/guard-lifecycle.md)
- [新项目接入条件](docs/project-admission.md) · [首次接入清单](docs/onboarding.md) · [接入路线](docs/roadmap.md)
- [契约草案提取 `contract draft`](docs/contract-drafts.md) · [CI 示例与 Summary](docs/github-actions.md)
- 实际试走数据见 [boltons 复跑记录](docs/results/onboarding-boltons-v1/README.md)

现状一句话：**已审核的本地快照、固定的 validators profile 能走完整链条；全新的独立项目能走受限接入链，但 Scope 还是精确快照，不会自动泛化到后续源码改动。** 详情看 [接入边界](docs/standalone-guards.md)。

## 开发

```powershell
uv run pytest -m "not slow" -q      # 快速层：不启动真实子进程
uv run ruff check .
uv run pytest -q --durations=20      # 完整套件，交付前跑一次
```

集成/e2e 测试、重型 fixture、真实子进程都标 `slow`。**快测会在准备、执行、清理三个阶段拒绝没标记的真实进程**——所以新测试只要起进程，就必须声明自己是 `slow`。见 [testing.md](docs/testing.md)。

## 项目结构

```text
src/counterguard/     实现与 CLI
tests/                单元、集成、端到端测试
schemas/              每个产物的 JSON Schema
benchmarks/           冻结的标注样本、拆分、模块上下文
examples/             Demo 场景、契约、实现
experiments/          冻结的实验协议
containers/           受限 Docker 执行器
docs/                 架构、数据契约、CLI、安全模型、已知限制
```

运行产物 `artifacts/` 和发行物 `dist/` 不进 Git。

## 安全与限制

CounterGuard 会**执行代码**、**读仓库**，所以它自己的安全姿态很重要：

- [security-model.md](docs/security-model.md)——资产、信任假设、仓库检查和容器执行的具体控制
- [attack-surface-checklist.md](docs/attack-surface-checklist.md)——逐项列出「已测 / 部分覆盖 / 完全没覆盖」
- [known-limitations.md](docs/known-limitations.md)——当前范围和历史验证边界

已有的验证用的是本地 Python 工具和固定的 Linux Docker 镜像。别把这些记录当成跨平台保证、恶意仓库隔离、签名认证或程序等价性证明。

## 许可

[Apache-2.0](LICENSE)
