# W3 安全模型与准入记录

基线：本地 MVP tag `v0.1.0`（`54b39d9`）；W3-A 增加只读检查，W3-B 的 Docker 执行尚未实现。[攻击面清单](attack-surface-checklist.md) 继续保留未关闭事项。本页不是通用沙箱或全面安全认证。

## 资产、输入和信任

可信：本机 Python、Pydantic、Git 可执行文件、调用者的 PATH/OS、工具源码与工作区权限。不可信：仓库的 Python、Git 配置/hooks、路径、引用、对象数据，以及可能来自仓库的项目配置。显式选择配置文件不等于它已经过语义审核。

保护宿主文件/凭据、历史产物、冻结数据、来源关联和“未执行”的语义。W3-A 只产生改动候选；所有报告与目标均为 execution_allowed=false，execution_outcome=not_run。没有 Guard 调度、Scope 判定、依赖安装、pytest 或目标模块导入。

## W3-A 的具体控制

1. 校验根路径与配置的既有组成部分，拒绝 symlink/Windows reparse point。只读普通 .git 目录；gitfile、worktree/commondir、reftable 等布局返回 unknown，不跟随外部 gitdir。
2. 受限读取 HEAD、heads/tags、packed-refs、shallow。对象目录预查链接/特殊文件、alternates 和体积；不读取原仓库 config、hooks、index 或 reflog。
3. 临时裸 Git 元数据由工具生成，仅复制校验后的引用/shallow。通过显式对象目录读原对象，cwd 不在被检仓库。关闭全局/系统配置，不继承 GIT_* 环境，关闭 replace、延迟获取、协议、可选锁和 fsmonitor。
4. 只运行 version、rev-parse、fsck、diff-tree、ls-tree、cat-file。修订受限并使用 --end-of-options；路径为 literal pathspec；diff 禁 external diff/textconv 和 rename 猜测，重命名为 D+A。
5. fsck 检查对象完整性；读取映射文件再核对 blob Git ID/长度，保存内容 SHA-256。提交/原始字节是事实来源，不使用 dirty working tree。Git symlink 拒绝，gitlink/子模块 unknown，不初始化。
6. 再读引用快照；变化时 unknown。输出固定原因码，不回显 Git stderr、绝对仓库路径或源码正文。绑定配置字节、选定提交、文件对象/内容与包源码摘要，不虚构时间。

选项依据 [Git 环境说明](https://git-scm.com/docs/git)、[修订校验](https://git-scm.com/docs/git-rev-parse)、[raw diff/过滤器](https://git-scm.com/docs/git-diff-tree) 和 [fsck](https://git-scm.com/docs/git-fsck)；不启用写 lost-found 的选项。实际覆盖以本项目测试为准，不能由选项名称推断安全。

## 资源与适用范围

| 项目 | W3-A v1 限额/规则 |
|---|---|
| 配置 | JSON 子集，128 KiB；128 目标，每目标最多 64 显式依赖 |
| 路径 | 512 字符，NFC、相对 POSIX；拒绝控制/格式字符、ADS/盘符、Windows 非法/保留名和遍历 |
| 元数据 | 每次目录遍历 16384 项；合成引用 2048；普通 SHA-1、ASCII heads/tags 与 HEAD/祖先语法 |
| 对象 | 存储文件合计 128 MiB；映射文件单个 1 MiB、累计读 8 MiB |
| Git 输出/时间 | 单次 stdout 2 MiB、stderr 64 KiB；单进程 5 秒，启动前核对 30 秒检查预算；超限 unknown |
| 影响范围 | 精确 source/contract/dependency refs；只显式忽略 .md/.rst；其他未映射改动 unknown |

ready 只代表指定提交可读且声明映射覆盖当前改动，不证明符号存在、契约业务语义、配置受信、依赖完整或 Guard 适用。unaffected 不是 Scope 的 inapplicable。删除/缺失 head 输入 unknown；新目标/契约仍需后续人工审核及真实验证。

不支持的合法布局/格式或缺失历史 unknown；越界/链接/损坏对象拒绝（退出 5），不自动修复、拉取或回退到全仓执行。过大仓库或不能通过 strict fsck 的旧对象也可能被保守拒绝，不宣称支持所有 Git 仓库。

## 攻击 fixture 与已测范围

| ID | 攻击/缺口 | 实现与测试 | 当前结论 |
|---|---|---|---|
| W02-A | 参数、路径、YAML/可执行配置、未映射改动 | project_config / change_analysis；test_project_config.py、test_change_analysis.py | 拒绝或 unknown，不产生执行许可 |
| W02-B | 原配置、环境、hooks、fsmonitor/过滤器 | repository；test_repository.py 的无效 config、恶意 helper、GIT_* 注入 | 不读原 config，marker 未生成 |
| W02-C | gitfile、alternates、junction/reparse、Git symlink、gitlink | test_repository.py 真实 Git/Windows junction | 拒绝或 unsupported unknown，不跟随/初始化 |
| W02-D | 缺提交、浅克隆、packed refs、损坏对象、引用变化 | test_repository.py | 不补历史/网络；损坏拒绝、变化 unknown |
| W02-E | 输出/时间超额、含凭据 stderr | test_repository_limits.py 的外部进程故障注入 | 固定原因码；不是实际恶意 Git fuzz |
| W02-F | dirty tree、重复读、三格式 | 真实 CLI；progress/w3a.md、results/w3a-v1 | 仓库字节/mtime 不变，未导入目标 |
| W01 | 文件/网络、CPU/内存/PID、子孙进程隔离 | W3-B Docker 待实现 | 未通过，未知代码执行仍禁止 |
| W03 | 插件/conftest、安装/build hooks | W3-B 待实现 | 未通过，当前未加载/安装/执行 |
| W04 | Registry/CI 权限与状态、公开日志 | W3-C/W4 待实现 | 未通过，inspect 不直接授权调度 |

## 剩余风险与准入

只读检查仍调用宿主可信 Git 的原生解析器。限额不是 OS 内存沙箱，也不能在阻塞文件系统调用或清理阶段保证严格墙钟上限；未证明抗 Git 压缩数据内存耗尽、Git 自身漏洞或任意后台子孙进程。未做全面 fuzz、全部平台/编码/文件系统矩阵。

路径/元数据检查不是 OS 原子快照；引用变化检测不证明抵抗恶意替换并恢复、权限攻击或全部 TOCTOU。摘要和 fsck 不认证作者/仓库身份，也不消除 SHA-1 与工具链的信任假设。

W3-B 必须用攻击 fixture 验收非 root、只读挂载/根文件系统、临时写目录、禁网、CPU/内存/PID/时间/日志上限、删除 capabilities、无宿主凭据和超时清理；配置/插件/安装也须覆盖。Git 控制面是否迁入受限环境需明确并实测，当前未做 OS 资源隔离。

W3-D 只有在 W3-A/B 待关闭项全部有实现版本、命令及实测记录后才能执行未知仓库；W3-C/W4 再关闭 Registry/CI 项。Docker 不可用或检查失败时，不以本地执行器替代。
