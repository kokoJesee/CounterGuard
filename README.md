# CounterGuard

让修过的缺陷，不再回来。

三个月前你修掉一个边界 bug。今天 AI 改同一份代码，它不知道这件事，于是同样的判断又漏了一次。

CounterGuard 的做法不复杂：每次确认修好的缺陷，顺手编译成一条可以重复执行的检查。这条检查知道自己该在哪些代码上生效，不会跑到无关模块里乱报。

> 中文 · [English](README.en.md)

当前公开版本是 [v0.5.0 Beta](https://github.com/kokoJesee/CounterGuard/releases/tag/v0.5.0)。Release 里有 wheel、源码包、两份带哈希的依赖清单、已审核的 runner 镜像和 SHA256SUMS，安装方法写在 [Beta 说明](docs/beta-release.md)。还没发布到 PyPI。

## 先装起来

```powershell
uv sync
uv run counterguard --help
```

从构建产物安装：

```powershell
uv build
python -m pip install "dist/counterguard-0.5.0-py3-none-any.whl[runner]"
```

wheel 里是 CLI 和库。真要跑测试，得装 `runner` 这个 extra，它会带上 pytest。缺 pytest 时命令会在写任何东西之前退出 `3`，并提示装 `counterguard[runner]`。

离线 Demo 还需要源码里的 `examples/`、`benchmarks/`、`experiments/` 和契约测试，这些不进 wheel。

## 跑一遍 Demo

```powershell
uv run counterguard demo --scenario examples/demo/mvp.yaml --workspace artifacts/quickstart-v1
```

一条命令走完捕获、编译、学边界、重放，写出 `report.json` 和 `report.md`。再执行一次同样的命令，只做只读校验并重新渲染报告。

场景文件虽然叫 `mvp.yaml`，解析器其实只认 JSON 子集，缩进、注释、锚点都不支持。合法输入和「缺契约 → unknown」的例子在 [快速开始](docs/quickstart.md) 里。

Demo 用提前录好的候选和本地 fixture，不联网，也不调用模型。它是演示，不是给任意 Python 代码用的沙箱。

## 三个结论，别混在一起

跑一条守卫，可能同时发生三件不同的事，CounterGuard 把它们分开记：

| 字段 | 取值 | 说的是什么 |
|---|---|---|
| `scope_decision` | `applicable` / `inapplicable` / `unknown` | 这条守卫该不该管这个目标 |
| `execution_outcome` | `not_run` / `pass` / `fail` / `error` / `timeout` | pytest 到底跑没跑、跑成什么样 |
| `final_verdict` | `pass` / `violation` / `skipped` / `inconclusive` | 最终给人看的结论 |

不适用和信息不足都不会启动 pytest，记 `not_run` 加 `skipped`；环境故障是 `inconclusive`。跳过的那一行，永远不会被算成通过。

报告里还能查到最小失败用例、initial/refined 规则、逐条 clause 的比对结果和来源链接，字段定义见 [CLI 契约](docs/cli.md)。

## 它怎么工作

1. **捕获。** 同一组用例分别跑 buggy 和 fixed 两个版本，只有「旧版真的失败、新版真的通过」才算一次可复现证据。原始日志、case 结果、目标与源码摘要都留着。
2. **编译。** 把失败的那几个 case 抽出来，生成只包含它们的 Guard，发布前先在 fixed 目标上自检。
3. **学边界。** Guard 该在哪些目标上生效，从已经确认的反例里学。学习器只拿到 `FeatureVector` 和一个适用性布尔值，路径、名字、期望值这些会泄题的东西一律不进训练。
4. **重放。** 先判适用性，再决定跑不跑 pytest。跳过的行里 `run` 是 `null`。

## 冻结的 15 个样本

`benchmarks/` 里有 15 个带标注的目标：9 个训练、6 个留出。两个守卫：

- **会员折扣**（`membership_discount` v1 final-price）：会员按原价 80% 结算，金额保留两位小数、四舍五入（half-up），负数金额拒绝。编译出的 Guard 只留源缺陷上失败的那两个会员价 case。
- **查询上限**（`input-limit` v1）：默认 20，只接受 1–100 的 ASCII 十进制数字串；带符号、补零、Unicode 数字、畸形和超范围都拒绝。Guard 只留「拒绝 0」这一条断言。

作用域特征里刻意不含契约 ID、路径、模块名、目标名和期望输出。留出集里还放了一个「不适用但违反自己契约」的目标，用来说明「该不该管」和「对不对」是两件事。

### 学出来的条件

`initial` 阶段，两条规则都只学到 `contract_version == v1`。加入两个冻结的合法反例重新训练后，条件变成版本加接口：折扣是 `final_price`，查询是 `query_parameter`。

9 个训练样本上的结果：

| 阶段 | TP | FP | TN | FN |
|---|---:|---:|---:|---:|
| initial | 4 | 2 | 3 | 0 |
| refined | 4 | 0 | 5 | 0 |

搜索空间分别是 8/92 和 10/175 个候选组合。输入随机打乱 20 次，规则和摘要不变；留出样本不参与拟合。

```powershell
uv run counterguard scope learn --protocol experiments/scope_v1.json --phase initial --output artifacts/.../initial
uv run counterguard scope learn --protocol experiments/scope_v1.json --phase refined --output artifacts/.../refined
```

## 留出集上的四种方法

```powershell
uv run counterguard benchmark replay --protocol experiments/scope_v1.json --phase refined --split train
uv run counterguard experiment evaluate --protocol experiments/scope_v1.json --split holdout --fitted artifacts/experiments/scope-v1/fitted --output artifacts/experiments/scope-v1/final
```

训练重放预期退出 `1`：有两条适用目标确实违反了 Guard。这一轮 2 通过、2 违规、5 跳过，只启动 4 次 pytest。

6 个留出目标上的结果：

| 方法 | TP / FP / TN / FN | 错误应用率 | Bug Recall |
|---|---|---:|---:|
| always | 2 / 4 / 0 / 0 | 1.0 | 1/1 |
| fixed interface | 2 / 2 / 2 / 0 | 0.5 | 1/1 |
| learned initial | 2 / 2 / 2 / 0 | 0.5 | 1/1 |
| learned refined | 2 / 0 / 4 / 0 | 0.0 | 1/1 |

refined 把两次错误应用改掉了，两个真正适用的目标都还在，也没有新增 FP/FN。query 守卫没有留出缺陷，所以它的 Bug Recall 是 `null`，不是 100%。

unknown 在冻结口径里按负预测处理，但它的比率和决策覆盖率会单独报，原始结果里保留 unknown。

`evaluate` 退出 0 只表示实验达到冻结验收标准，不代表每条 Guard 都通过。这 6 个标签已经公开，所以它是工程验证，不是盲测。

`replay verify` 不跑 pytest，只审当前输入是否完整。审核通过说明记录齐全，不说明当时的结论是 pass。

## 退出码

`capture`、`compile`、`learn`、`replay run`、`evaluate` 都支持 `--format text|json|markdown`。显式指定格式会把原始 payload 包进 `command-report.v1`；不传就保持原来的 JSON，格式化不影响退出码。

| 码 | 含义 |
|---|---|
| `0` | 可复现 Evidence，或验收通过 |
| `1` | 做完了但没复现；或适用 Guard 确认违规 |
| `2` | 输入非法 |
| `3` | 执行故障（包括缺 pytest 元数据） |
| `4` | 信息不足（unknown）；或学习拒绝泛化 |
| `5` | 产物完整性失败 |

pytest 自己的 2–5、缺失或歧义的 case、超时，都不算「可复现缺陷」。

## 更多文档

- [统一仓库验证 `verify`](docs/verify.md) · [Guard 生命周期](docs/guard-lifecycle.md)
- [只读控制台](console/README.md)：导出本地 Registry 和运行产物后，在浏览器里看守卫、验证记录和适用范围
- [新项目接入条件](docs/project-admission.md) · [首次接入清单](docs/onboarding.md) · [接入路线](docs/roadmap.md)
- [契约草案提取 `contract draft`](docs/contract-drafts.md) · [CI 示例与 Summary](docs/github-actions.md)
- boltons 的实际试走记录：[复跑记录](docs/results/onboarding-boltons-v1/README.md)

现在的边界是这样：已审核的本地快照和固定的 validators profile 能走完整链条；全新项目可以走受限接入链，但 Scope 仍然是精确快照，不会自动泛化到后续源码改动。细节见 [接入边界](docs/standalone-guards.md)。

## 开发

```powershell
uv run pytest -m "not slow" -q      # 快速层，不启动真实子进程
uv run ruff check .
uv run pytest -q --durations=20      # 完整套件，交付前跑一次
```

集成、e2e、重型 fixture 和真实子进程都标了 `slow`。快速层会在准备、执行、清理三个阶段拒绝没有标记的真实进程，所以新测试只要起进程，就得声明自己是 `slow`。规则见 [testing.md](docs/testing.md)。

## 目录

```text
src/counterguard/     实现与 CLI
tests/                单元、集成、端到端测试
schemas/              每个产物的 JSON Schema
benchmarks/           冻结的标注样本、拆分、模块上下文
examples/             Demo 场景、契约、实现
experiments/          冻结的实验协议
containers/           受限 Docker 执行器
console/              只读控制台（守卫、验证记录、适用范围）
docs/                 架构、数据契约、CLI、安全模型、已知限制
```

运行产物 `artifacts/` 和发行物 `dist/` 不进 Git。

## 安全

CounterGuard 会读仓库、也会执行代码，所以它自己的安全边界值得单独看：

- [security-model.md](docs/security-model.md)：资产、信任假设、仓库检查、容器执行的控制
- [attack-surface-checklist.md](docs/attack-surface-checklist.md)：已测、部分覆盖、完全没覆盖，逐项列出
- [known-limitations.md](docs/known-limitations.md)：当前范围和历史验证的边界

已有的验证跑在本地 Python 工具和固定的 Linux Docker 镜像上。别把这些记录当成跨平台保证、恶意仓库隔离、签名认证或程序等价性的证明。

## 许可

[Apache-2.0](LICENSE)
