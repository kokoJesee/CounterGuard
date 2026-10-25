# CounterGuard

让修过的缺陷，不再回来。

AI 改代码时，并不知道你以前修过什么。同一个 bug，会被它一遍又一遍改回来。CounterGuard 把每次确认修好的缺陷编译成一条可以重复执行的检查，再学出这条检查该在哪些代码上生效。

> 中文 · [English](README.en.md)　|　[v0.5.0 Beta](https://github.com/kokoJesee/CounterGuard/releases/tag/v0.5.0)　|　还没上 PyPI

## 试一下

```powershell
uv sync
uv run counterguard demo --scenario examples/demo/mvp.yaml --workspace artifacts/quickstart-v1
```

一条命令走完捕获、编译、学边界、重放，写出 `report.json` 和 `report.md`。离线运行，不调用模型。

要装 wheel 并真正跑测试：

```powershell
uv build
python -m pip install "dist/counterguard-0.5.0-py3-none-any.whl[runner]"
```

`runner` 这个 extra 会带上 pytest；没装时命令会在写任何东西之前退出 `3`。Demo 还需要源码里的 `examples/`、`benchmarks/`、`experiments/`，这些不在 wheel 里。

场景文件虽然叫 `mvp.yaml`，解析器只认 JSON 子集，合法输入见[快速开始](docs/quickstart.md)。

## 和普通回归测试的区别

普通测试记住了断言，却不知道这条断言该不该搬到另一段代码上。搬得太宽，正确的代码被误报；搬得太窄，历史缺陷又溜回来。

CounterGuard 的适用边界不是手写的，而是从已经确认的合法反例里学出来的。学出来的条件只看代码特征，不看路径、名字或期望值。

## 三个结论分开记

| 字段 | 取值 |
|---|---|
| `scope_decision` | `applicable` / `inapplicable` / `unknown` |
| `execution_outcome` | `not_run` / `pass` / `fail` / `error` / `timeout` |
| `final_verdict` | `pass` / `violation` / `skipped` / `inconclusive` |

不适用和信息不足都不会启动 pytest，记录是 `not_run` 加 `skipped`。跳过永远不会被算成通过。字段定义见 [CLI 契约](docs/cli.md)。

## 一次修复会变成什么

1. **捕获。** 同一组用例跑旧版和新版，旧版失败、新版通过，才算可复现证据。
2. **编译。** 只保留失败的那几个 case，形成最小 Guard，先在 fixed 目标上自检。
3. **学边界。** 用已经确认的反例训练适用条件，留出样本不参与拟合。
4. **重放。** 先判适用性，再决定跑不跑 pytest；跳过的行 `run = null`。

## 现在有什么

15 个标注目标（9 训练 / 6 留出），两个守卫：会员折扣和查询上限。

在 6 个留出目标上，加入反例后的规则把错误应用从 2 次降到 0 次，两个真正适用的目标都还在。这 6 个标签已经公开，所以它是工程验证，不是盲测。完整数字和口径见[评测说明](docs/evaluation.md)。

## 控制台

仓库里带了一个静态控制台，双击就能看：

```powershell
python console/tools/export_console_data.py --root .
start console/index.html
```

导出数据带着本机路径，已经被 `console/.gitignore` 排除，新克隆的仓库要先跑一次。页面里能看守卫、每次重放、适用性判断和告警，说明见[控制台文档](console/README.md)。

![控制台总览](console/shots/01-overview-real.png)

## 边界

现在能跑的是 Python 3.12 起、pytest 8.4、根目录或 `src/` 布局、零运行时依赖的项目；仓库代码在审核过的 Docker 镜像里执行。

它不是任意 Python 项目的沙箱，也还不能自动泛化到后续源码改动。这里的验证记录不代表跨平台保证、恶意仓库隔离或签名认证。

## 更多文档

- [仓库验证 `verify`](docs/verify.md) 和 [Guard 生命周期](docs/guard-lifecycle.md)
- [接入条件](docs/project-admission.md)、[接入路线](docs/roadmap.md)、[boltons 试走记录](docs/results/onboarding-boltons-v1/README.md)
- [安全模型](docs/security-model.md)、[攻击面清单](docs/attack-surface-checklist.md)、[已知限制](docs/known-limitations.md)

## 开发

```powershell
uv run pytest -m "not slow" -q      # 快速层
uv run ruff check .
```

会启动真实进程的测试要标 `slow`，规则见 [testing.md](docs/testing.md)。

## 许可

[Apache-2.0](LICENSE)
