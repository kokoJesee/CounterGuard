# 学习规则的研究重放（实验接口）

工具自有 fixture 的训练结果可以接入研究重放。新入口是 `StudyFittedSession.audit / replay / verify`，复用原研究重放器的物化、Docker 运输、运行前后审核和原始 JUnit 核验。

它不接入生产 Registry，也不批准外部目标或正式 scope_v2 评测。

## 版本与共同准入

新格式独立存于 [research-v2](../schemas/research-v2/)：plan、review、admission、replay 为 v2，
Docker authorization 为 v7。旧 v1/v6 模型和 Schema 保持原样，旧 parser 拒绝新记录；
旧 v1 learned 方法仍返回 unknown。训练侧的 fit/Scope 保持 `execution_allowed=false`，
不能凭裸规则或自摘要取得执行权限。

所有方法先重建同一 source/Guard、固定 target、原 oracle 映射、runner/policy、两份 fit 和特征对账。两份 fit 必须分别是 initial 和 refined，绑定同一 source、Guard、protocol、split 和拟合审核。

重放核验两份 fit 时会读各自的训练成员；initial 规则仍然只由 initial 成员拟合，holdout 没有读取入口。查询目标只提供 context/audit，不接受查询适用性标签。

训练与查询共用实际定义核验：direct 绑定文件与符号，static-reexport-v2 绑定静态解析到的真实定义，
闭包中同名 helper 不能代替目标。context 的接口类别也必须与执行审核一致。
人工元数据、标签与调用映射的语义仍由可信操作者判断，字节一致不等于语义正确。

| 方法 | 共同准入后的行为 |
|---|---|
| `b1_always` | 适用；安全检查不被绕过 |
| `b2_interface` | 仅比较获审 source 接口和 query context 的接口；不偷用 version 或标签 |
| `learned_initial` | 对查询 FeatureVector 计算已核验 initial Scope 的原条款 |
| `learned_refined` | 同样计算 refined Scope |

原 `conjunction.v1` 搜索、并列裁决和逐条件反例见证不变。执行侧与生产 Scope 共用纯条款 evaluator，
但研究 Scope 不转成生产 Scope。admission 保留 Scope 摘要、逐条件 trace、原始三态决定与原因。
若所选 fit 是可重建的 refusal，返回 unknown 与原 refusal_code，`scope_digest=null`；
不会把它解释为空规则或不适用。特征不支持或人工对账不一致也停止执行。

## 两条独立的信任锚

调用方须在可变 plan 之外分别持有：

1. 拟合审核摘要 `fit_review_anchor`：允许消费获审 protocol/split/training，不能批准执行。
2. 执行审核摘要 `review_anchor`：由 `issue_fitted_review` 生成新事件，绑定原 source/target/map/见证、
   source/target 接口、runner/policy/全包实现，再绑定两份 fit、拟合审核、query context/audit 摘要。

plan 只列引用，不能声明 decision、label、Scope 摘要或许可。
运行前后独立重建的 v7 授权绑定上述事实、实际 admission、source H、target revision、
原最小 case/test/request/input origins 和精确镜像；只有 applicable 才进入共享 Docker 执行器。
result 另存两个可信摘要，verify 不能用结果中的自述替代调用方的信任锚。
审核输出与运行输出必须位于 workspace 内、source/target/所有训练仓库之外，且不能覆盖已有结果。

审核事件是可信本机操作记录，没有身份签名、远程角色、自动发现最新撤回或密码学防回滚。
撤回时须显式提供新事件摘要；同时控制两个锚、验证器和主机的攻击不在保证内。

## 使用方式

准备来源链、[研究训练](study-fit.md)和查询特征后，使用
[study_fitted.py](../src/counterguard/study_fitted.py) 的 `issue_fitted_review` 创建新的执行审核。
构造 `StudyFittedSession(source_repo, target_repo, workspace, execution_anchor, fit_session)`，
其中 fit_session 持有独立拟合锚及显式训练仓库映射。完整可执行示例见
[自有 Git/Docker 专项](../tests/integration/test_study_fitted.py)。

源码仓库根的命令：

```powershell
uv run python scripts/run_scope_study.py audit --workspace <workspace> --source-repo <source> --target-repo <query> --review-digest <execution-anchor> --fit-review-digest <fit-anchor> --training-repository <training-clone> --plan <v2-plan.json>
uv run python scripts/run_scope_study.py replay --workspace <workspace> --source-repo <source> --target-repo <query> --review-digest <execution-anchor> --fit-review-digest <fit-anchor> --training-repository <training-clone> --plan <v2-plan.json> --output <new-directory>
uv run python scripts/run_scope_study.py verify --workspace <workspace> --source-repo <source> --target-repo <query> --review-digest <execution-anchor> --fit-review-digest <fit-anchor> --training-repository <training-clone> --result <v2-result.json>
uv run python scripts/export_study_fitted_schemas.py --check
```

尖括号替换为实际输入；多个训练仓库重复 `--training-repository`。
v2 缺少独立拟合锚会被拒绝，v1 不接受这些新参数，不能静默忽略。
audit 不发现 Docker；inapplicable/unknown 重放也不发现或启动 Docker，`run=null`，
分别保存 `skipped_inapplicable` / `skipped_unknown`，绝不显示为通过。
退出码沿用研究重放：0 为完成观察或核验（含 inapplicable/test_failed），3 为执行故障，
4 为 unknown，5 为来源/输入完整性失败，2 为参数错误。
verify 的 0 仅证明记录可重建，不把 unknown/refusal 或失败改成成功。

## 重新物化与结论边界

新增源码改变全包实现指纹。需要当前执行结论时，在新目录以新 ID 重建
binding → Evidence → Guard → source → training context/audit/fit review/fit → execution review → replay。
source H 内容未变时可以复用 H，不伪造新的仓库提交。只改 map/query/fit 等输入也必须重建其全部下游，
旧结果、旧 Schema、冻结数据和标签不覆盖。固定输入的规则和决定可重复，真实审核/运行时间与随机 run ID 不伪装成相同。
运行后发现输入变化保留实际 Run 并标记 stale；重签摘要不能通过独立 verify。

本接口只验证工程链条；合成 fixture 的 version/interface 规则及差异不能证明真实跨项目收益。
外部目标、来源重捕获、独立语义标签/谱系分组、正式协议与留出评测需要各自准入。
尚无外部研究计数或最终对照结论。完整本批实测范围见
[验收记录](results/research-fitted-replay-v1/README.md)。
