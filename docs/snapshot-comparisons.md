# 工具自有的独立快照比较

`research-snapshot comparison` 将[独立研究快照](research-snapshots.md)的最小 Guard 重放到另一个固定提交的工具自有目标上。来源的原输入、异常和消息不变；目标自身的 oracle 独立观察，不替换原 Guard。

用途固定为 `tool_owned_snapshot_comparison_only`。这不是外部项目授权、生产 Scope 或正式研究数据；旧快照/研究/Registry parser 不接受这些新格式。外部用途须采用独立类型、实现和批准，不能给真实仓库添加 fixture 标记以绕过边界。

另有[独立外部观察 API](external-snapshot-observations.md)，不改变本页命令的 fixture 限制。

## 两条观察分开

| lane | 执行内容 | 能说明什么 |
|---|---|---|
| `guard` | 来源最小 Guard 的全部 case；输入、关键字、异常、消息原样 | 此 Guard 在这个获审目标上的实际结果 |
| `own_contract` | 同样的输入与来源身份，使用单独审核的目标 oracle | 对目标固定规范所列性质的独立观察 |

目标 witness 必须覆盖整个最小 case 集，并绑定目标提交里非空的规范或测试依据。不能改输入、参数次序、case ID、原断言身份、源码行或参数索引，只能声明另一条 oracle。

预期值暂时只支持现有的原语标量；异常和字面量 match 复用原白名单，复杂正则、额外适配器和自定义调用代码都不支持。

`own_contract` 仅允许获审的 B1。它的通过不产生适用性/合规性标签，不声称目标整个 API 正确，也不使来源 Guard 的失败自动成为缺陷。当前 witness 不增加独立 stdout oracle；已有 stdout 研究接口仍是另一套明确版本。

## 来源、目标与映射

- 来源必须从真实自有 B/F/H、原契约、Evidence/最小 Guard、自检授权及原始 JUnit 重建，并通过独立的来源执行审核锚。
- 目标保存完整 Git manifest、完整包 refs、入口/显式导入根、LICENSE 摘要及接口声明依据。检查完整提交，工作区删文件/改代码不能替换它。
- 当前映射仅为 `identity_call_all_minimal_cases`：逐 case 绑定完整源 case 摘要，不改位置参数或关键字，不删 case，不加入 source control、wrapper 或参数转换。
- 目标自身的配置、原测试/conftest 不挂载；整个包与数据文件都挂载。源包不进入目标容器，契约仍是来源 H 的原始 blob。

目标 `execution_allowed=false` 固定，不是一个可打开的开关。目标检查和自摘要不赋予执行权限。完整快照的容量、Git、Python/依赖/原生文件和普通包边界沿用独立快照规格；比较目标另拒绝与工具控制目录相撞的大小写变体。

接口字段只接受 `value_return` / `stdout_write`。来源接口由可信本机审核者声明并指向 F 的实际包文件；目标接口也有其提交内依据。这是待审元数据，不是扫描器对运行语义的证明，不能由 Guard 结果倒推或直接用作研究标签。

## 独立审核与执行

比较审核另绑定来源审核锚、Guard/绑定、目标/完整 manifest、完整映射、可选自身 witness、runner/policy、超时和当前实现。调用方必须独立保留比较审核摘要；它与来源执行审核摘要分开。替换可变文件并重算自摘要不能替换任一锚。

方法行为为：

| 方法 | 本接口行为 |
|---|---|
| `b1_always` | 共同安全门通过后 applicable |
| `b2_interface` | 仅比较来源与目标的接口声明；相同执行，不同 inapplicable |
| `learned_initial` / `learned_refined` | 此新快照命名空间尚未绑定 fit，明确 unknown，reason=`comparison_snapshot_fit_not_bound` |

其他研究 profile 已有的 fit 不会借此适用于新来源。计划不能携带伪造的 `fit_ref`；新快照的拟合适配是后续独立工作。没有用手工条款替代 learned 方法。

unknown/inapplicable 写 `run=null`，没有运行目录、授权或执行记录，也不构造测试或发现 Docker；不会显示成 passed。撤回审核为 unknown。损坏/不同锚在执行前拒绝。

实际执行沿用原 `_AdmittedDockerProcess` 和封闭 DockerPolicyV1：精确已审核镜像、无网络、非 root、只读、固定 PID/内存/输出/时间限额，不安装依赖，不增加环境或本地 fallback。运行前后重建全部来源与授权，结果可独立从 Git、两个锚、规范测试和原始 JUnit 重建。

晚到的输入/来源变化保留实际 Run、标 stale，独立 verify 拒绝；不把已执行结果伪装成零启动。新输出须在工作区内且在两个仓库之外，预检 240 UTF-16 路径预算及原子发布/runner sandbox 路径，不改变机器长路径设置。

## 命令与检查

```powershell
counterguard research-snapshot comparison --help
counterguard research-snapshot comparison inspect-target --help
counterguard research-snapshot comparison map --help
counterguard research-snapshot comparison review --help
counterguard research-snapshot comparison run --help
counterguard research-snapshot comparison verify --help
uv run python scripts/export_snapshot_comparison_schemas.py --check
```

run 支持 `--audit-only`，只重建并给决定；该模式仍须提供 output 参数，但不创建它。普通 run 输出原始结果并以 0/1/3/4/5 区分 passed 或 inapplicable、真实断言失败、执行故障、unknown、完整性错误；verify 的 0 仅说明记录可重建，不改写其原 verdict。

新模型位于 `snapshot_comparison_models.py`，Schema 在 `schemas/snapshot-comparison-v1/`；不重写旧 Schema。源码变化使旧执行链过期，当前结论必须用新 ID/目录重建，不能补签历史产物。

自有资格测试：

```powershell
uv run pytest tests/unit/test_snapshot_comparison.py -q
uv run pytest tests/integration/test_snapshot_comparison_data.py -q
# 按 runner list 核验的 root-pytest8 精确 ID 设置环境变量后：
uv run pytest tests/integration/test_snapshot_comparison_docker.py -q
```

integration 两项均标 slow，Docker 项另标 docker；未设置镜像变量时 skip 不算验收通过。实际结果与拒绝范围见[验收回执](results/snapshot-comparison-fixture-v1/README.md)。
