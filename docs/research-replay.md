# 研究重放（实验接口）

这个接口用于工具自有 fixture 的工程验证。它把来源 Guard 与另一个固定目标的调用映射分开，
共同复用已审核 Docker runner，不改变生产 standalone 的精确 B/F 快照 Scope。
它不是任意仓库接入、正式 scope_v2 实验、外部目标执行批准或生产 Registry 调度入口。

## 已实现的范围

| 方法／输入 | 当前行为 |
|---|---|
| `b1_always` | 共同来源、审核和隔离准入通过后执行；不能绕过安全检查 |
| `b2_interface` | 仅比较人工审核绑定的 fixture 接口类别 `value_return` / `stdout_write` |
| `learned_initial` / `learned_refined` | 返回 unknown，原因 `study_fit_interface_not_implemented`，不启动 Docker |
| `lane=guard` | 用来源最小失败 case 的原 oracle 观察目标 |
| `lane=witness` | 仅允许获审的独立 `stdout_eq` 见证和 `b1_always`；不替换来源 oracle |

`tool-fixture-interface.v1` 只描述自有 fixture，不是外部研究的最终 interface_kind 词汇表。
正式研究的特征、fit、split、接口分类和标签尚未接入，不能根据此接口的测试结果宣称精化有效。

## 来源与审核

`study_data.inspect_source` 独立重建当前来源 B/F/H、Evidence、最小 Guard 及其真实日志和自检。
`inspect_target` 从目标完整固定提交重建 import 闭包、导出与钩子信息、源码和许可文件 pins。
目标可以只有一个固定提交，不补造 B/F/H。许可文件存在不等于自动完成许可合规审核。

`make_call_map` 只允许对最小 case 的关键字作一一映射；位置参数、字面量值、异常和消息 oracle 均取自来源。
唯一可显式留下不转发的来源控制是字面量 `force_color=True`。
不允许适配器解包、夹紧或截断元组，不接受自定义 Python、期望值或 applicable 标记。
映射的语义正确性仍须人工审核，字段一致性不能代替语义。

可信本机操作者用 `issue_review` 生成全新、不可覆盖的审核事件，绑定 source/target/map/见证、
全包源码、已审核 runner 和封闭 policy。批准或撤回事件可引用先前事件，读取时核对链和摘要。
调用方须在可变计划文件之外保留返回的审核摘要，并作为 `--review-digest` 显式传入。
从计划读出的自摘要不能自行获得执行权限；撤回后应使用新事件的摘要。

本机操作者文本不是身份签名，也没有远程角色认证、自动发现最新事件或密码学防回滚。
若攻击者能同时替换可信审核摘要、代码和运行环境，这些摘要不能保护执行。
source Guard 在 Registry 中仍可保持 Candidate，研究审核不提升 Shadow/Active，也不改变生产可调度状态。

## 使用 Interface

Python Interface 是 `StudySession.audit(plan)`、`replay(plan, output)`、`verify(result_path)`。
Session 持有来源仓库、目标仓库、工作区和单独保存的可信审核摘要。
输入准备函数位于 [study_data.py](../src/counterguard/study_data.py)，严格模型位于
[study_models.py](../src/counterguard/study_models.py)。一份完整的可执行自有示例见
[Docker 专项](../tests/integration/test_study_bridge.py)。它现场创建两个独立 Git 历史，没有下载或执行第三方项目。
配套 [JSON Schema](../schemas/research-v1/) 可用 `uv run python scripts/export_study_schemas.py --check` 核对；
业务不变量仍以严格模型和来源重建为准，JSON Schema 自身不构成批准。

已有获审 fixture 数据和 `study-replay-plan.v1` 后，在源码仓库根运行：

```powershell
uv run python scripts/run_scope_study.py audit --workspace <workspace> --source-repo <source-clone> --target-repo <target-clone> --review-digest <trusted-review-digest> --plan <plan.json>
uv run python scripts/run_scope_study.py replay --workspace <workspace> --source-repo <source-clone> --target-repo <target-clone> --review-digest <trusted-review-digest> --plan <plan.json> --output <new-directory>
uv run python scripts/run_scope_study.py verify --workspace <workspace> --source-repo <source-clone> --target-repo <target-clone> --review-digest <trusted-review-digest> --result <result.json>
```

尖括号替换为实际值。plan/result 的相对路径相对于 workspace，输出须是 workspace 内、两个仓库外的全新目录。
原 `inventory` 子命令仍只读核对历史公开事实，不触发任何研究执行。

## 结果与失败语义

准入／Scope／执行结果分别保存。inapplicable 和 unknown 都不发现或启动 Docker，`run=null`，
结果分别为 `skipped_inapplicable`、`skipped_unknown`，不会显示成 pass。
适用时只挂载目标闭包、原样的 source H 契约和可信生成测试；授权 v6 显式区分 source/target 来源。
源契约的 target 字段不改写。新授权不能交给旧生产 parser，新数据也不自动进入生产 replay。

执行前后均重建来源、审核和输入，核对精确镜像、封闭 policy、request、原始 JUnit、版本及日志。
中途发现变化时保留实际 Run，标记 stale／integrity_error，不能回填成未启动或通过。
完整性失败、未知、基础设施错误和 test_failed 分开；test_failed 只是一次来源 oracle 的观察，不能自动称为回归。

目标在收集阶段 import，位于 raises oracle 之外；import-time ValueError 不会被当成成功复现。
stdout 见证使用有界 StringIO 与 redirect_stdout 收集输出，最多 8192 字符，单条期望最多 4096 字符；
不改输入、不捕获目标异常、不 monkeypatch 目标。Observer 自身失败记为基础设施错误。
见证可能只覆盖获审 case 的子集；通过也不会自动生成 `contract_compliant` 或任何研究标签。

退出码：0 表示调用完成／事实核验完成（包括明确的 test_failed 观察和 inapplicable），
2 为参数错误，3 为执行基础设施错误，4 为 unknown，5 为完整性或输入损坏。
verify 的 0 不把负结果改成正结论；stale 结果不会通过当前来源核验。

## 摘要与验证范围

新增包源码会改变全包 implementation_digests，既有来源链按原规则过期。
需要消费当前实现时，用新 ID 重建 binding → capture → Guard → research source/target/map/review → replay，
不重签或覆盖旧产物。原 H blob 内容未变时可复用 H，不为代码指纹变化伪造新的所有者提交。
冻结 scope_v1、benchmarks/examples、旧 artifact、旧 Schema 和发布标签保留，不新增运行时依赖。

常规执行快速层与专项目录；完整来源链的 transport-double 测试也标 slow，避免拖慢日常循环。
真实进程只在标记 slow/docker 的自有专项中启动。没有运行全量时不声称全量通过。
本批实测与保留的失败记录说明见[自有 fixture 验收](results/research-bridge-v1/README.md)。

独立的[研究特征提取与对账](study-features.md)已提供 For/GeneratorExp 的静态处理和纯 learner 输入投影。
它没有扩写本页的 v1 plan/admission 或 v6 authorization；缺少 fit/scope/协议绑定时 learned 方法仍然 unknown。

[研究训练拟合](study-fit.md)已提供独立 protocol/split/sample/审核/fit/Scope 与来源重建，
但尚未绑定本页执行授权。其 `execution_allowed=false`，C1 learned replay 仍明确 unknown，不能直接传入新 fit 获得执行。
