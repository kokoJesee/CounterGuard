# 受限外部快照观察

该实验接口将来源 Guard 的原断言用于**另行获审的固定第三方快照**，并可执行独立 stdout 见证。
它只支持 B1 无作用域观察，不训练、不创建研究标签、不冻结实验协议，也不接入生产 Registry 调度。
它不能用来声称 Guard 适用、目标满足全部规范或已经发现目标回归。

## 独立的接受范围

[严格模型](../src/counterguard/study_observation_models.py)使用独立新版本：
plan/review/admission/result 为 v3，Docker authorization 为 v8，Schema 位于
[research-observation-v1](../schemas/research-observation-v1/)。
purpose 固定 `external_snapshot_observation_only`；旧 fixture-only v1/v2/v6/v7 不修改，旧 parser 拒绝新记录。
plan 的 method 只能为 b1_always，必须引用非空的获审见证；不能传入 fit、训练仓库、标签、批准布尔或环境变量。

调用方用 `issue_observation_review` 进行可信本机审核，单独保存返回的 review anchor。
新审核绑定当前 source/Guard/Evidence/B/F/H、固定 target 全树/闭包、全部最小 case 映射、
独立见证、简单 I/O 类别、runner/policy、全包源码和可选前序审核事件。
该事件不认证远程身份，不自动发现最新撤回，也不提供密码学防回滚。
同时控制可信 anchor、代码与主机的攻击不在保证内。

原 source 契约仍必须是 H 的真实 blob。目标只提供自己的固定提交，不伪造目标 B/F/H。
全部来源最小失败 case、位置参数、字面量与异常/消息 oracle 保留；仅允许原映射 grammar 的关键字改名，
以及明确记录的 source-only force_color=True。不在适配器夹紧、拆包、补齐或吞掉目标异常。

见证可以是获审子集，但不能替换或裁剪 Guard。见证输入仍来自原 case，只有预期 stdout 另有独立规范依据。
`lane=guard` 使用完整 Guard；`lane=witness` 单独使用获审子集，两者结果分别保存。
stdout 使用原有有界 StringIO/redirect_stdout，目标 import 在 oracle 之外；不加载上游测试、插件、conftest 或安装脚本。
环境、镜像和 DockerPolicyV1 不因新用途放宽。

## 结果解释与核验

`StudyObservationSession` 复用原 StudySession 的来源重建、最小物化、Docker transport、
执行前后重新授权和原始 JUnit 核验，未增加本地 executor 或另一套容器命令。
只有独立外部审核与当前共同准入通过，B1 才可执行。
admission 的 `scope_interpretation=execution_policy_not_semantic_label` 明确它是执行政策，不是适用性标签。

撤回审核返回 unknown、run=null，零启动；损坏输入拒绝。
执行后发现变化保留实际 Run 并 stale；verify 重新加载原事实和真实日志，不相信重签的内部自摘要。
test_failed 只表示来源 oracle 的观察失败；见证 passed 只覆盖其获审 case。
任何结果都不能自动设置 whole-Guard applicability 或 whole-target contract compliance。

CLI 仍用显式版本路由：

```powershell
uv run python scripts/run_scope_study.py audit --workspace <workspace> --source-repo <source> --target-repo <target> --review-digest <external-review-anchor> --plan <v3-plan.json>
uv run python scripts/run_scope_study.py replay --workspace <workspace> --source-repo <source> --target-repo <target> --review-digest <external-review-anchor> --plan <v3-plan.json> --output <new-directory>
uv run python scripts/run_scope_study.py verify --workspace <workspace> --source-repo <source> --target-repo <target> --review-digest <external-review-anchor> --result <v3-result.json>
uv run python scripts/export_study_observation_schemas.py --check
```

v3 不接受 `--fit-review-digest` 或 `--training-repository`。没有自动 approve 命令。
退出码沿用研究接口：0 为完成观察或核验（包括 test_failed），3 为执行故障，4 为 unknown，
5 为完整性/输入失败，2 为参数错误。verify 的0不能提升科学结论。

源码变化令需要当前结论的旧链 stale，须用新 ID 重建 source binding/capture/Guard/review/观察；
H 原始内容未变可复用 H，不能重签旧产物或因此新造所有者提交。
改 source/target/map/见证/审核/runner/policy 也须重做全部相关下游。
真实时间和 run ID 保留，不伪装跨运行相同；固定输入的决定及逐 case 计数可独立比较。

具体固定目标的观察需要单独授权。工具自有资格测试不计外部样本；任何外部运行记录都应列清
固定提交、规范/映射依据、审核锚、实际容器数、未裁决输入与数据暴露，不将部分见证通过充作正式 Scope 评测。

已完成的[termcolor → colored 固定观察](results/colored-observation-v1/README.md)列出工具自有资格项、
独立外部批准、8 次真实外部容器、两 lane 重复结果及未裁决范围。
