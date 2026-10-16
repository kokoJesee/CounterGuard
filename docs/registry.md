# 本地 Registry

Registry 的 add/list/show/disable 只登记和审核已有 Guard，不捕获 Evidence、不执行测试、不决定 Scope，也不提升为 Active。`enabled` 表示允许进入后续核验候选，不等于生命周期 Active。[生命周期事件](guard-lifecycle.md)另行记录人工审阅状态，[verify](verify.md)仅自动调度 Shadow/Active。

```powershell
uv run counterguard registry add artifacts/guards/<guard-id>/guard.json --cwd <source-workspace> --root .counterguard
uv run counterguard registry list --root .counterguard --format json
uv run counterguard registry show <guard-id> --root .counterguard --with-evidence
uv run counterguard registry disable <guard-id> --root .counterguard --reason "manual review"
uv run pytest tests/unit/test_registry.py tests/integration/test_registry_cli.py -q
```

`add/list/show/disable` 支持 json/text/markdown，默认 JSON。完整性异常返回 5，未知 ID/参数返回 2；show/list 的来源损坏行仍输出 `integrity=invalid`、`schedulable=false` 和 reason_code 后返回 5。禁用可以对已损坏来源执行，且是终态；重复 add 或 disable 不恢复它，也不重写已有时间/事实。

持久化布局：

```text
.counterguard/
  registry.json             # 不可变 registry 身份
  entries/<guard-id>.json   # Guard/Evidence 快照、原工作区/ref/原文件摘要
  events/00000001.json      # 全局追加序列、前驱摘要、Guard 摘要、操作者/时间/原因
  registry.sqlite3         # 可重建索引 + 同序列追加事件镜像
```

JSON 是事实来源。SQLite UPDATE/DELETE 触发器拒绝原地改写事实与事件，每次操作逐项比对 SQLite 和 JSON；不把 SQL 中的 enabled 当作可信授权。进程中断造成 JSON 已发布、索引未提交时拒绝调度，不能自动覆盖“修复”。保留损坏 DB 后，可在无并发操作时移走 DB，再显式运行 `registry rebuild-index`；重建需要完整合法 JSON 历史，禁用状态保留。删失事实/事件或冲突历史不能靠重建变绿。

登记后仍保留原工作区，不复制、重签或重写任何既有 Evidence/Guard/log。每次 `resolve_for_execution` 都重新调用完整 `verify_guard` 与 `verify_evidence`，核对 Guard/原始 JUnit/源码/契约/来源身份和登记快照；原工作区移动、缺失或变动即拒绝。这是有意的本地实现约束，不是可携带备份格式。调度器必须在执行前调用这个入口，并另行完成 Scope、Inspection 和 Docker 授权；直接调用 LocalTrustedExecutor 不构成 Registry 调度。

操作者是本机审计文本，不认证身份；原登记/禁用事件沿用本机账户名或宿主标签，新生命周期事件默认使用 `local-operator`。单用户工作区权限是信任假设。可以同时改写整个 Registry、全部来源和验证器的本机管理员，或回滚整份目录的攻击，不由本地 hash/SQLite 解决。签名、权限角色、撤销、防回滚、CI 凭据/上传、公开日志和多平台发布仍未关闭。缺失索引始终拒绝，不在正常 list/show 时自动重建。
