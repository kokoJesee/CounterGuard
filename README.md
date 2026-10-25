# CounterGuard

让修过的缺陷，不再回来。

CounterGuard 是一个 Python 回归守卫工具。它把一次已确认的修复（旧版失败、新版通过）编译成只包含失败 case 的最小检查，再从已确认的合法反例里学出这条检查该作用在哪些代码上。

> v0.5.0 Beta · Apache-2.0 · [English](README.en.md) · 未上 PyPI

## 安装

```powershell
uv sync
uv run counterguard --help
```

要跑测试，装带 `runner` extra 的 wheel：

```powershell
uv build
python -m pip install "dist/counterguard-0.5.0-py3-none-any.whl[runner]"
```

## 快速开始

```powershell
uv run counterguard demo --scenario examples/demo/mvp.yaml --workspace artifacts/quickstart-v1
```

输出：

```text
demo accepted: true
Replay executions: 4
verdict_counts: {"pass": 2, "skipped_inapplicable": 2, "violation": 2}
```

加 `--verify-only` 再跑一次，只核对已有记录，不启动 pytest。

Demo 离线运行，用仓库里的示例和本地 fixture，不调用模型。场景文件叫 `mvp.yaml`，但只支持 JSON 子集，合法格式见[快速开始](docs/quickstart.md)。

## 它是怎么工作的

1. **捕获**：同一组用例跑旧版和新版，只有旧版失败、新版通过才算证据。
2. **编译**：只保留失败的那几个 case，生成 Guard，并在新版上自检。
3. **学边界**：用已确认的反例训练适用条件。路径、名字、期望值都不进入特征。
4. **重放**：先判适用性，再决定跑不跑 pytest。

结果分三层记录：`scope_decision`（适用 / 不适用 / 未知）、`execution_outcome`（未执行 / 通过 / 失败 / 异常 / 超时）、`final_verdict`（通过 / 违规 / 跳过 / 无法判断）。不适用和未知都不启动 pytest，跳过不会算成通过。

## 实验结果

15 个标注目标（9 训练 / 6 留出），两个守卫：会员折扣和查询上限。

加入两个已确认反例后，留出集上的错误应用从 2 次降到 0 次，两个适用目标都保留。标签已公开，属于工程验证。数字和复现命令见[评测说明](docs/evaluation.md)。

## 控制台

```powershell
python console/tools/export_console_data.py --root .
start console/index.html
```

静态页面，展示守卫、重放记录、适用范围和告警。导出数据含本机路径，已被 `.gitignore` 排除。说明见[控制台文档](console/README.md)。

![控制台总览](console/shots/01-overview-real.png)

## 已知限制

- 只支持 Python 3.12+、pytest 8.4、根目录或 `src/` 布局、零运行时依赖的项目；
- 仓库代码只在审核过的 Docker 镜像里执行，不是任意代码的沙箱；
- 新项目的 Scope 是精确快照，不会自动泛化到后续改动；
- 尚未发布到 PyPI。

## 文档

- [CLI 与退出码](docs/cli.md)
- [仓库验证 `verify`](docs/verify.md)、[Guard 生命周期](docs/guard-lifecycle.md)
- [接入条件](docs/project-admission.md)、[接入路线](docs/roadmap.md)、[boltons 试走记录](docs/results/onboarding-boltons-v1/README.md)
- [安全模型](docs/security-model.md)、[已知限制](docs/known-limitations.md)

## 开发

```powershell
uv run pytest -m "not slow" -q
uv run ruff check .
```

会起真实进程的测试标 `slow`，规则见 [testing.md](docs/testing.md)。

## 许可

[Apache-2.0](LICENSE)
