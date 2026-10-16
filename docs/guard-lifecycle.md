# Guard 生命周期

Guard 的测试内容与 Evidence 来源保持不可变；生命周期通过 Registry 中的新事件记录，不修改 `guard.json` 中的初始 `state=candidate`。

允许的转换为 Candidate→Shadow/Retired、Shadow→Active/Retired、Active→Shadow/Retired。其他转换，包括重复状态、跳过 Shadow 和从 Retired 复活，一律拒绝。再次启用需要新 Guard 版本。Registry 的 disabled 是另一条终态，不能通过生命周期转换、重复 add 或索引重建恢复。

```powershell
uv run counterguard guard transition <guard-id> --to shadow --reason "reviewed source chain" --root <registry>
uv run counterguard guard transition <guard-id> --to active --reason "accepted replay results" --actor reviewer --root <registry>
uv run counterguard guard history <guard-id> --root <registry>
```

事件使用 `guard-lifecycle-event.v1`，包含 Registry 身份、全局序号、Guard/Evidence 摘要、前后状态、操作者、真实 UTC 时间、原因、前驱摘要和自身摘要。它与原 `registry-event.v1` 共用追加式 JSON/SQLite 事件链；旧登记和禁用事件的字节不变，SQLite 不新增第二份权威状态。读取或索引重建时重新核对合法转换、身份、来源摘要、顺序和 SQLite 镜像。

提升为 Shadow/Active 前重新审核来源。来源已过期时仍允许追加 Retired，方便止用；这不会把来源完整性变成通过。退休后的 Guard 也不能通过旧 Registry 执行解析入口调度。

`verify` 只自动调度 Shadow/Active：Shadow 违规只记录，Active 的适用且确认违规结果返回 1。`registry list/show` 的 `verification_schedulable` 明确表达这个策略；旧 `schedulable` 仅表示来源可进入原有审核入口，不代表 Active。现有直接 smoke-run 或手动 pilot 入口不能作为生命周期自动调度的替代品。

操作者只是本机审计标签，默认 `local-operator`，不读取账户名作为新生命周期事件的默认值。该记录没有认证用户身份、校验角色或签名，也不能阻止有权重写整份 Registry 的本机管理员回滚历史；这些仍未关闭。不要把一个本地 Active 事件解释成远程 CI 的权限凭据。

每次 verify 另外记录所用 Scope 的 basis/digest；本版生命周期不持有学习 Scope，也不制造空的 Scope 授权。未来加入持久 Scope 绑定时必须使用新事件版本，明确变更和重算范围。
