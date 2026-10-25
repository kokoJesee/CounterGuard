# 获审外部快照的独立观察

这个接口让可信的本机操作者先审核完整源码快照，再在已审核的 Docker 里捕获真实 B/F、编译最小 Guard，并观察另一个固定目标。它使用独立的 `external-snapshot-*.v1` 类型，用途固定为 `reviewed_external_snapshot_observation_only`。

原来的 [fixture 接口](research-snapshots.md)和[自有比较](snapshot-comparisons.md)保留原类型和标记要求，不接受外部审核、Evidence、Guard 或比较计划。没有新增 `allow_external` 开关，也不能靠给真实仓库加 fixture 标记来取得执行权限。

## 接受范围和材料

源码范围沿用 `source-only-python-snapshot.v1`：完整 Git manifest、完整普通包及其资源，
PEP 621 静态零运行时依赖、受支持 Python 版本；不安装依赖、不运行 setup、原始测试、
conftest 或插件。Git、容量、路径和已有 Docker policy 的限制不变。

契约和 binding 是只读声明，不赋予执行权限，可以使用现有 `research-snapshot prepare/bind`。
来源仍须满足 F 的唯一父提交是 B，H 的唯一父提交是 F；H 仅新增原测试机械提取的契约及已声明工具配置。
上游源码、测试、资源和许可原样保留，契约必须来自 H 的实际 blob。

来源外部审核另声明 GitHub 仓库 URL 和 LICENSE pin，核对 B/F/H 的许可字节一致且非空。
URL 是可信操作者的声明，不证明远端所有权；许可是否合法、契约是否符合规范仍需人工审阅。
URL 不接受凭据、查询参数、其他协议或其他主机。

执行审核会绑定完整 binding、runner、policy、预算、超时和当前全包源码指纹。调用方要单独保存审核摘要，不能从候选文件或可变计划里自行读取批准。

`ExternalSnapshotSession` 只允许 `external_snapshot_capture` 和 `external_snapshot_guard_check`，没有精确源重放、Registry、Shadow/Active 或本地 fallback 路径。

## Python 接口

本版提供 Python API，没有新增外部用途 CLI；旧命令仍只批准自有 fixture。
以下是接口示意，路径和可信审核依据须由操作者提供：

```python
from counterguard.external_snapshot import (
    ExternalSnapshotSession,
    issue_external_snapshot_review,
)

review = issue_external_snapshot_review(
    repo, binding_path,
    repository_url=reviewed_fork_url,
    license_ref="LICENSE",
    reason=reviewed_execution_basis,
    output=review_path,
)
# 将 review.artifact_digest 作为独立可信锚保管；不从待执行计划取回它。
source = ExternalSnapshotSession(repo, workspace, binding_path, review_path, trusted_anchor)
evidence = source.capture(evidence_id=new_evidence_id, output=new_capture_directory)
guard = source.compile(
    new_capture_directory / "evidence.json",
    guard_id=new_guard_id,
    output=new_guard_directory,
)
```

capture 保留全部原 case；reproduced 只有在 B 真正断言失败且 F 全通过、case 集完整时为真。
Guard 恰好保留实际失败子集，并在 B/F 自检。基础设施错误不作为缺陷；失败记录及原始 Run 保留。
`verify_evidence` / `verify_guard` 从 Git、独立审核锚、测试和原始 JUnit 重建，不启动容器。

## 外部目标和两个 oracle

`external_snapshot_comparison.py` 提供：

- `inspect_external_snapshot_target`：固定提交、完整 manifest/包、独立 URL/许可/接口依据；execution_allowed 固定 false。
- `create_external_snapshot_map`：最小 Guard 全部 case 的 identity call，不删 case、不改输入或原 oracle。
- `ExternalSnapshotWitness`：相同输入/身份，另声明目标自己的 oracle，固定规范依据必须来自目标提交。
- `issue_external_comparison_review`：另一个独立可信审核锚，绑定来源审核、Guard、目标、map、witness、runner 和预算。
- `ExternalSnapshotComparisonSession.run/verify`：使用原封闭 Docker transport 执行或独立重建。

本用途只接受 B1 观察，lane 为 `guard` 或 `own_contract`；B2 和 learned 方法在输入校验时拒绝。
它不是完整四方法研究评测，不生成标签、训练、fit、split、正式协议或生产 Scope。
目标自身 oracle 的通过不替换源消息，也不自动使来源 Guard 的失败成为误报或缺陷。

撤回审核为 unknown，run 和运行引用为 null，不渲染测试或发现 Docker。
错误来源/比较锚、改输入、删 case 或来源漂移拒绝；运行后才变化则保留实际 Run、标 stale，verify 拒绝。
新源码使旧链过期，须在新 ID/目录重建；不重签历史结果。

## 资格测试与限制

```powershell
uv run pytest tests/unit/test_external_snapshot.py -q
uv run pytest tests/integration/test_external_snapshot.py -m "not docker" -q
# 设置 COUNTERGUARD_RUNNER_IMAGE_DIGEST 为 runner list 核验过的精确 ID 后：
uv run pytest tests/integration/test_external_snapshot.py -m docker -q
uv run python scripts/export_external_snapshot_schemas.py --check
```

integration 全部标 slow，Docker 项另标 docker。缺镜像变量的 skip 不算通过。
资格测试只使用工具自有、无 fixture 标记的仓库；外部用途类型的资格不等于任何真实仓库已执行。

此接口不提供远程签名身份、自动发现最新撤回、防回滚、跨会话容器总配额，
也不能防止恶意目标在容器内干扰测试结果。独立审核、实际容器账本及规范裁决仍需操作者负责。
新模型、独立审核锚和 Docker 隔离不证明目标业务语义，也不证明项目之间没有代码借用。

固定 [TerminalTextEffects → webcolors 实测](results/tte-webcolors-observation-v1/README.md)
在该边界下完成 8 个真实外部容器：来源捕获/自检各 2，目标原 Guard/自身 oracle 各 2。
结果只增加一条行为观察，不产生标签、fit、holdout 或正式研究结论。
