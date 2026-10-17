# CounterGuard 0.5.0 Beta

将一份经人工审核、位于目标 head 的契约串联为可复验的回归 Guard：

- Docker 双向 Evidence，仅保留 buggy 实际失败的 case；最小 Guard 在 buggy/fixed 两侧自检。
- 精确完整源码闭包的快照 Scope；未知快照保留 unknown，不执行、不显示通过。
- 追加式 Candidate → Shadow → Active → Retired 生命周期及本地 Registry；仅显式审核状态可调度。
- 统一 verify JSON/Markdown 和有限字段 CI Summary，保留 Shadow/Active/unknown 的退出语义。
- 哈希固定的 wheel、工具依赖清单、已审核 root runner 归档及可复制的人工触发 workflow。

安装和完整实测见 [Beta 文档](https://github.com/kokoJesee/CounterGuard/blob/v0.5.0/docs/beta-release.md)
与[验收记录](https://github.com/kokoJesee/CounterGuard/blob/v0.5.0/docs/results/beta-v0.5.0/README.md)。
下载后先核对 SHA256SUMS；基础 wheel 不带 pytest，本地 Demo 使用 runner 依赖清单和源码包内示例。
仓库目标只在 Docker 执行。

当前为受限 Python 根/src 布局、零运行时依赖与字面量 oracle；快照 Scope 不代表对任意修改的学习泛化。
validators 是固定 MAC 缺陷试点，其 owner head 原始 bundle 因身份元数据仅保留本地，
不宣称新机器能自动取得全部试点来源。通用路径另外用工具自有 Git/Docker fixture 验证。

不包含任意项目 pytest 插件/fixture 加载、目标依赖安装、远程 Registry 授权、自动 Active、
GitHub App 或自动 PR 执行。workflow 是可复制模板，未在 GitHub 托管 runner 上实测；本地同驱动验收与平台实测分开。
摘要不提供签名或所有者身份认证，Docker 不证明恶意目标未干扰 JUnit。

项目许可 Apache-2.0；validators 来源 MIT；镜像内基础发行版及依赖保留各自许可。
冻结 scope_v1、既有产物和 v0.1.0 标签保持原样。本次不向 PyPI 发布。
