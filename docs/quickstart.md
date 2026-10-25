# 从离线 Demo 开始

Demo 不需要联网，也不调用模型。它会完整跑一遍捕获、编译、学边界和重放，把结果写到你指定的目录。

## 准备环境

从源码安装会带上 dev 组里的 pytest：

```powershell
git clone https://github.com/kokoJesee/CounterGuard.git
cd CounterGuard
uv sync --frozen
uv run counterguard --help
```

也可以先构建 wheel，再装到要运行 CLI 的 Python 环境：

```powershell
uv build
python -m pip install "dist/counterguard-0.5.0-py3-none-any.whl[runner]"
```

`runner` extra 提供 pytest。只装基础 wheel 就运行 Demo，会得到退出码 3 和 `pytest runner is unavailable`，不显示 traceback，也不会创建输出目录。缺 Demo 的源码输入时，装 runner 也补不上，还需要源码分发里的 `examples`、`benchmarks`、`experiments` 和 `tests/contract_tests`。

预构建 wheel 的下载、摘要核对和隔离安装见 [Beta 说明](beta-release.md)，checkout 之外的完整安装见[安装与发布验收](release.md)。

## 跑 Demo

```powershell
uv run counterguard demo --scenario examples/demo/mvp.yaml --workspace artifacts/quickstart-v1
uv run counterguard demo --workspace artifacts/quickstart-v1 --format json
uv run counterguard demo --workspace artifacts/quickstart-v1 --format markdown
uv run counterguard demo --workspace artifacts/quickstart-v1 --verify-only
```

第一次会生成 `report.json`、`report.md` 和完整来源链。之后再执行同一目录只做只读复验并重新渲染；输入、代码或依赖版本变了，换一个 `quickstart-v2` 这样的新目录。失败和部分完成的目录也保留原样，不靠覆盖旧文件恢复。

## 场景文件必须是 JSON

文件虽然叫 `mvp.yaml`，读取器只支持 JSON 语法这一 YAML 子集，不支持通用 YAML：双引号、花括号、方括号可以，缩进键值、注释、锚点、尾逗号都不行。文件扩展名不会启用 YAML 解析，项目也不会为此引入 PyYAML。

可读取的完整场景和仓库示例一致：

```json
{
  "schema_version": "pipeline-scenario.v1",
  "scenario_id": "scope_v1_offline_v1",
  "protocol_ref": "experiments/scope_v1.json",
  "guards": [
    {
      "guard_id": "grd_discount_member_rate_regression_v2",
      "request_ref": "examples/demo/requests/discount_agent.json",
      "replay_sample_ids": ["train-v1-source-bug", "train-v1-fixed", "train-v1-discount-amount"]
    },
    {
      "guard_id": "grd_query_limit_zero_regression_v2",
      "request_ref": "examples/demo/requests/query_agent.json",
      "replay_sample_ids": ["train-query-v1-source-bug", "train-query-v1-fixed", "train-batch-v1-legal"]
    }
  ]
}
```

下面这种 YAML 写法当前会被拒绝，即使它本身是合法 YAML：

```yaml
# 不支持注释和缩进映射
scenario_id: scope_v1_offline_v1
protocol_ref: experiments/scope_v1.json
```

解析失败返回 2，提示需要 JSON-compatible YAML，Pipeline 不会开始，也不会创建输出。正确的 JSON 还必须符合 `pipeline-scenario.v1`：只能选择冻结 scope_v1 的两份 Guard 和已列举的训练成员。不要改协议、标签或期望值来定制演示，完整字段见 [CLI 文档](cli.md)。

## 结果怎么读

标准 Demo 的六行都来自冻结训练成员，目标、声明契约和 context 都完整，所以结果是 2 个 violation、2 个 pass、2 个 skipped_inapplicable。它不是 unknown 分支的实证，也不是新的留出实验。

`unknown` 表示信息不足，和已经确认的 `inapplicable` 不同。想实际看一次 unknown，可以在新 workspace 里跑一个缺少声明契约的重放：

```powershell
uv run counterguard replay run --guard artifacts/guards/grd_discount_member_rate_regression_v2/guard.json --scope artifacts/fitted/refined/grd_discount_member_rate_regression_v2.json --target examples.discount.implementations.final_price_v1_fixed:calculate_price --cwd artifacts/quickstart-v1/w --artifact-root artifacts/unknown-example --format json
```

这条命令故意不传 `--contract`，预期退出 4：报告是 `scope_decision=unknown`、`execution_outcome=not_run`、`final_verdict=skipped`，payload 里 `verdict=skipped_unknown`、`run=null`，并说明缺少目标契约元数据。它走的是公开 Replay 路径，但不会启动 pytest。不要补上 `--contract` 之后又把结果叫成同一个 unknown 案例。

新的 ReplayResult 保存在该 workspace 的 `w/artifacts/unknown-example/replays/<replay_id>/result.json`，具体 ID 在 JSON payload 里。用 `replay verify` 加 `--cwd` 指向同一个 `w/` 就能审核这条记录。它是独立诊断案例，不改写标准六行 Demo，也不改 scope_v1 的分母。

每次 `replay run` 都会创建新 ID。要展示同一次结果的不同格式，请从已验证的 JSON 渲染，不要为了换格式再跑一次。更多错误码和分享边界见 [CLI 文档](cli.md) 与[已知限制](known-limitations.md)。
