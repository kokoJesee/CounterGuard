# 从离线 Demo 开始

当前版本支持 Python / pytest 和受信本地示例。先选择安装方式，再在源码输入根目录使用一个尚不存在的输出目录。

## 两种安装方式

本地 MVP 尚未上传 PyPI，以下使用 [冻结发行物](release.md) 的真实 wheel 路径：

```powershell
# 基础安装：CLI、数据模型与库；不安装 pytest 执行器。
python -m pip install './dist/v0.1.0-freeze/counterguard-0.1.0-py3-none-any.whl'

# 执行安装：需要运行 Demo、Capture 或 Guard 时选择 runner。
python -m pip install './dist/v0.1.0-freeze/counterguard-0.1.0-py3-none-any.whl[runner]'
```

安装源提供同名包后，对应包名写法分别是 `python -m pip install counterguard` 和 `python -m pip install "counterguard[runner]"`。两者是可选方式，不必先装基础包再装 runner。uv 用户可以使用 `uv pip install` 加相同的 wheel/extra 参数；请安装到实际运行 CLI 的 Python 环境。

基础安装缺少 pytest 时，新 Demo 返回 **3**，给出 `pytest runner is unavailable` 和安装 `counterguard[runner]` 的提示，不显示 traceback、不启动 pytest、不创建输出目录。CLI 的 version/help 仍可使用。若缺少 Demo 的源码输入，安装 runner 不能替代输入文件；需保留源码分发中的 examples、benchmarks、experiments 和 tests/contract_tests。

## 从源码开始 Demo

源码开发安装会包含 dev 组中的 pytest：

```powershell
uv sync
uv run counterguard demo --scenario examples/demo/mvp.yaml --workspace artifacts/quickstart-v1
uv run counterguard demo --workspace artifacts/quickstart-v1 --format json
uv run counterguard demo --workspace artifacts/quickstart-v1 --format markdown
uv run counterguard demo --workspace artifacts/quickstart-v1 --verify-only
```

完整的独立安装及 checkout 外运行命令见 [安装与发布验收](release.md)。

首次调用会生成 report.json、report.md 和完整来源链。后续调用只读复验；输入、代码或依赖版本改变后使用 quickstart-v2 等新目录。失败/部分目录也保留原样，不通过覆盖旧文件恢复。

## mvp.yaml 的内容必须是 JSON

**文件虽然叫 mvp.yaml，当前读取器只支持 JSON 语法这一 YAML 子集，不支持通用 YAML。** 使用双引号、花括号和方括号；不支持 YAML 的缩进键值、注释、锚点，也不支持 JSON 尾逗号。文件扩展名不会启用 YAML 解析。当前不引入 PyYAML 等新运行时依赖。

下面是可读取的完整场景内容，和仓库示例相同：

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

以下常见 YAML 写法**当前会被拒绝**，即使它本身是合法 YAML：

```yaml
# 当前不支持注释和缩进映射
scenario_id: scope_v1_offline_v1
protocol_ref: experiments/scope_v1.json
```

解析失败返回 2，提示 JSON-compatible YAML；尚未开始 Pipeline 或创建输出。正确 JSON 还必须符合 pipeline-scenario.v1：只能选择冻结 scope_v1 的两份 Guard 及已列举的训练成员。不要修改协议、标签或期望值来定制演示。完整契约见 [CLI 文档](cli.md)。

## 怎么读结果，以及为什么标准 Demo 没有 unknown

标准 Demo 的六行来自冻结训练成员，均有完整的目标、声明契约和已审计 context，所以得到 2 个 violation、2 个 pass、2 个 skipped_inapplicable。它不是 unknown 展示分支的实证，也不是新的留出实验。

unknown 表示缺少足够信息，和已经确认 inapplicable 不同。可以在上面的新 workspace 中实际运行一次缺少声明契约的重放：

```powershell
uv run counterguard replay run --guard artifacts/guards/grd_discount_member_rate_regression_v2/guard.json --scope artifacts/fitted/refined/grd_discount_member_rate_regression_v2.json --target examples.discount.implementations.final_price_v1_fixed:calculate_price --cwd artifacts/quickstart-v1/w --artifact-root artifacts/unknown-example --format json
```

这条命令有意省略 --contract，预期退出 **4**；报告为 scope_decision=unknown、execution_outcome=not_run、final_verdict=skipped，payload.verdict=skipped_unknown、payload.run=null，并说明缺少目标契约元数据。它确实调用公开 Replay 路径，但不会启动 pytest。不要给这条命令补 --contract 后又把结果称为同一个 unknown 案例。

新的 ReplayResult 保存在该 workspace 的 w/artifacts/unknown-example/replays/&lt;replay_id&gt;/result.json；JSON payload 给出具体 replay_id。用 replay verify 加 --cwd 指向同一个 w/ 审核该记录。它是独立诊断案例，不改写标准六行 Demo 或 scope_v1 的分母。

每次 replay run 都创建新 ID；需要展示同一次结果的不同格式时，从已验证 JSON 渲染，避免为切换格式制造新执行。更多错误码、原始证据和公开分享范围见 [CLI 文档](cli.md) 与 [已知限制](known-limitations.md)。
