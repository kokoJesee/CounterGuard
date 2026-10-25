# Guard 生命周期

Guard 的测试内容和 Evidence 来源不可变。状态变化只通过 Registry 里的追加事件记录，不改 `guard.json` 里的初始 `state=candidate`。

允许的转换只有这些：

- Candidate → Shadow / Retired
- Shadow → Active / Retired
- Active → Shadow / Retired

重复设置同一状态、跳过 Shadow、从 Retired 复活，都会被拒绝。要重新启用，得发一个新的 Guard 版本。Registry 的 disabled 是另一个终态，不能被生命周期转换恢复，也不能靠重复 add 或重建索引恢复。

```powershell
uv run counterguard guard transition <guard-id> --to shadow --reason "reviewed source chain" --root <registry>
uv run counterguard guard transition <guard-id> --to active --reason "accepted replay results" --actor reviewer --root <registry>
uv run counterguard guard history <guard-id> --root <registry>
```

事件格式是 `guard-lifecycle-event.v1`，记录 Registry 身份、全局序号、Guard / Evidence 摘要、前后状态、操作者、真实 UTC 时间、原因、前驱摘要和自身摘要。它和原来的 `registry-event.v1` 共用同一条追加式 JSON / SQLite 事件链；旧登记和禁用事件的字节不变，SQLite 也不会多出第二份权威状态。读取或重建索引时会重新核对合法转换、身份、来源摘要、顺序和 SQLite 镜像。

提升到 Shadow 或 Active 之前，要重新审核来源。来源已经过期时仍然允许追加 Retired，方便先把 Guard 停用，但这不会把来源完整性变成「通过」。退休后的 Guard 也不能再通过旧 Registry 的执行解析入口被调度。

`verify` 只自动调度 Shadow / Active 两种状态：Shadow 违规只记录，Active 的「适用且确认违规」返回 1。`registry list/show` 里的 `verification_schedulable` 表达的就是这个策略；旧字段 `schedulable` 只表示来源可以进入原有审核入口，不代表已经是 Active。

操作者只是本机的审计标签，默认 `local-operator`，不会去读账户名。它不认证用户身份、不校验角色、也不签名；本机管理员如果能重写整份 Registry，仍然可以回滚历史。不要把本地的一条 Active 事件解释成远程 CI 的权限凭据。

每次 verify 还会记录所用 Scope 的 basis 和 digest。本版生命周期不持有学习到的 Scope，也不会制造空的 Scope 授权。将来加入持久 Scope 绑定时，要用新的事件版本，把变更和重算范围写清楚。
