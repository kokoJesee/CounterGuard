# 统一验证入口

`counterguard verify` 从提交差异选择已登记的历史 Guard，检查状态和适用性后，通过 Docker 重放并写出同源 JSON/Markdown 报告。它不生成新测试，不调用模型，不使用本地执行器作为回退。

```powershell
uv run counterguard guard transition <guard-id> --to shadow --reason "reviewed source chain" --root <registry>
uv run counterguard runner list
uv run counterguard verify --repo <repo> --base <base-sha> --head <head-sha> --config <project-config.json> --registry <registry> --runner docker --runner-id root-pytest8 --output artifacts/verify/check-v2
```

占位符需要替换为同一来源链的实际路径和完整 SHA。`runner list/show` 提供审核来源与本机可用状态；`--runner-id` 自动绑定精确 image ID，原 `--image` 只接受目录中的已审核 ID，两者二选一，不能传浮动 tag。详见 [runner 发现](runners.md)。输出目录必须位于当前工作区内、目标仓库之外，且尚不存在；重新检查使用新输出 ID。

## 状态与选择

Registry 的 `enabled` 与生命周期状态独立。新登记的 Guard 为 Candidate；只有 Shadow 和 Active 进入自动重放。Candidate、Retired、disabled 和未受影响目标分别给出跳过原因，`run=null`；这些行不会显示为通过。Retired 与 disabled 不能复活。

Registry 的来源损坏、索引与 JSON 不一致，即使发生在 Candidate 上也不能被跳过策略掩盖。执行前后重新审核来源与 Registry 状态；执行后发生禁用或输入变更时保留实际 RunRecord，报告完整性失败。

## 当前支持的适用性

本版使用 `verified-evidence-source-snapshot.v1`：只接受经独立 Evidence/Guard 审核的原 buggy 或 fixed 源码字节、同一契约字节和已审核符号。仅支持 `guard.v1`、`project-config.v1` 的根导入布局、无项目依赖映射且只含标准库静态导入的目标。

完整 head 树先经过 no-install profile 的静态预检；conftest、插件、依赖安装需求和需要人工复核的动态代码均不自动执行。只有声明的提交输入与经核验的 Guard 测试进入 Docker 挂载。

该规则是有限的已审核快照绑定，不是程序等价性证明，也不是 Scope 学习或跨提交泛化。其他源码字节、依赖闭包、导入布局或仓库 Guard 格式均为 unknown。文件影响范围的 unaffected 仅用于筛选，不会被改写为 Scope 的 inapplicable。

冻结 `scope_v1` 的学习器和评测入口保持原样。统一 verify 现在也接入固定 validators 的 `guard.v2` / `src` / pytest9 profile：使用 `--runner-id validators-pytest9`，从登记来源重验 owner manifest、完整提交树、契约与依赖闭包，校验 `pilot-scope.v1`，再在本次输出下创建新运行目录和 `docker-execution-authorization.v3`。仅限原审核的 base/head/config，不把旧试点成功结果当作对其他 head 的授权。

新的 `pilot-manifest.v3` 明确使用现有 owner head 中的历史文件名 `evidenceguard.yaml`；不修改该提交、文件或契约，也不建立新的 owner 提交。旧 manifest、Evidence、Guard 和授权保留原字节；当前实现的来源在新目录重捕获。其他 `src` 项目不因此自动获准，接入前置与估算见 [新项目条件](project-admission.md)。

## 独立字面量 Guard（Beta）

Beta 新增[独立字面量 Guard](standalone-guards.md)：`guard.v3`、Registry entry v3，以及精确 B/F 完整闭包的 Scope。

- 支持受审核的普通模块/包根布局和 `src/` 布局，使用 root-pytest8 runner；
- 映射必须精确，契约必须来自 head，依赖闭包不能混合两个快照；
- 只有来源核验通过的 Shadow / Active 可调度，执行前后都要重验 Registry、提交和授权；
- 其他快照保持 unknown / 4、`run=null`。

含这个 profile 的 Registry 会产生 `verify-report.v3`；旧的 v1 / v2 报告结构和判定语义保留。

## 报告与退出码

新输出包含 `inspection.json`、需要时的 `preflight.json`、`report.json`、`report.md`，以及实际执行行的 `work/<target-id>/authorization.json`、`run.json` 和原始日志。报告使用独立 `verify-report.v2`，增加 runner ID/image/review 摘要及固定仓库 Scope；旧 `verify-report.v1` 模型与 Schema 保留。报告逐行保留 Guard/Evidence/登记摘要、生命周期、影响状态、Scope、执行结果、最终判定及未判断原因。原始来源引用相对于登记时的来源工作区；运行日志引用相对于该行的 `run_workspace_ref`。

| 退出码 | 条件 |
|---:|---|
| 0 | 没有阻断结果；可能只有跳过或 Shadow 违规，必须查看计数 |
| 1 | Active 且适用的 Guard 确认违规 |
| 2 | 配置或其他输入非法、不可用 |
| 3 | Docker、执行请求或测试基础设施异常 |
| 4 | 未判断的影响或适用性；包括缺失映射、未审核 profile |
| 5 | Registry、来源、执行前后输入等完整性失败 |

多类结果同时出现时，优先级为 **5 → 3 → 4 → 2 → 1 → 0**。所有已知输入和领域失败均先写报告，再返回退出码；参数解析失败、输出目录不可写或已存在时无法发布新报告，不覆盖旧文件。

`counts.rows` 是 Guard/target 行数，`counts.guards` 是去重 Guard 数。unknown、skipped、execution_error、integrity_error 分别计数；`shadow_violations` 与 `blocking_violations` 分开。JSON 是事实来源，Markdown 和终端展示由同一模型渲染。

`artifact_digest` 包含真实时间、实现摘要和运行记录；重复运行不应伪造相同的完整摘要。`decision_digest` 只摘要排序后的来源与决策、Scope、执行类别和计数，不包含运行 ID、耗时或日志路径，可比较相同输入的独立运行。它提供完整性检查，不提供签名、独立身份认证或对恶意目标伪造 JUnit 的证明。

这些输出是本地审计记录，尚不是通用的公开脱敏导出格式。发布时只选择经审查的材料；保留个人开发规划和本机原始日志于本地。新增 `ci-report` 只从原 JSON 生成受限的公开计数/状态投影，重新核对呈现完整性但不重验来源或执行真实性；参见 [GitHub Summary](github-actions.md)。

## 验证

```powershell
uv run pytest -m "not slow" -q
uv run pytest tests/unit/test_verify.py tests/unit/test_lifecycle.py tests/unit/test_registry.py -q
# 设置已验收 root-profile runner 的完整 image ID 后运行真实 Git/Docker 专项
uv run pytest tests/e2e/test_verify.py -q
uv run ruff check .
```

真实进程测试标记为 `slow` / `docker`；没有显式设置 `COUNTERGUARD_RUNNER_IMAGE_DIGEST` 时跳过，跳过不计为已验收。
