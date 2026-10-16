# W3 安全模型与准入记录

更新：2026-10-16。本地 MVP tag `v0.1.0`（`54b39d9`）保留；W3-A 只读检查、W3-B 独立授权与受限执行、W3-C 本地 Registry 均已有记录。正式 runner 四项攻击与接受镜像字节锁定/恢复在 `1260b45` 通过；validators 在 `c9c8771` 的只读准入被阻断，未执行仓库代码。[攻击面清单](attack-surface-checklist.md) 保留未覆盖事项，本页不是通用沙箱或全面安全认证。

## 资产、输入和信任

可信：本机 Python、Pydantic、Git 可执行文件、调用者的 PATH/OS、工具源码与工作区权限。不可信：仓库的 Python、Git 配置/hooks、路径、引用、对象数据，以及可能来自仓库的项目配置。显式选择配置文件不等于它已经过语义审核。

保护宿主文件/凭据、历史产物、冻结数据、来源关联和“未执行”的语义。W3-A 只产生改动候选；`InspectionReport` 与 `TargetImpact` 的 Schema 把 `execution_allowed` 定义为 `const false`，代码中没有将其置真的路径。ready 不会翻转开关。

W3-B 使用另一份 `docker-execution-authorization.v1`。只有可信宿主控制面调用 `authorize_docker_execution`，同时复核当前检查器源码、Inspection 自摘要、配置原字节、ready/affected 且无不确定项、head 输入 Git/内容 pin、物化工作区、Guard 测试、精确 replay 请求、固定 Docker policy 和本地镜像 ID，才产生一次请求绑定。配置必须显式声明由 `source_ref` 唯一推导出的 Python `module`，防止执行时导入另一个可见模块。DockerExecutor 启动前和退出后都从这些可信来源重建授权；仅给 JSON 重算自摘要不够。仓库配置、被测 Python 和 Inspection 本身均不能授权，Docker 不可用或镜像身份不符也不会回退到 `LocalTrustedExecutor`。

这里的“可信宿主控制面”是进程内信任假设：当前库函数没有身份角色或签名认证。W3-C 保存本机登记/禁用事实并重验来源，不认证操作者身份。W4 仍须限制授权调用者并完善身份/签名/CI 权限，不能把任意拥有宿主 Python 执行权的调用者视为已鉴权。

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
| 影响范围 | 精确 source/contract/dependency refs；ignored_paths 必须逐路径声明，且只接受文档、根级许可证/变更日志/仓库元数据和少量 CI 控制文件；其他未映射改动 unknown |

ready 只代表指定提交可读且声明映射覆盖当前改动，不证明符号存在、契约业务语义、配置受信、依赖完整或 Guard 适用。unaffected 不是 Scope 的 inapplicable。删除/缺失 head 输入 unknown；新目标/契约仍需后续人工审核及真实验证。

一个 PR 同时修改源码和 `.github/workflows/ci.yml` 时，只有配置把这个**精确路径**放入 `ignored_paths` 才得到 affected/ready；没有声明则 unknown。允许声明的是直接位于 `.github/workflows/` 的 yml/yaml、`.github/dependabot.yml|yaml`、`.circleci/config.yml`、根级 `.gitignore`/CI 元数据，以及文档/许可证/变更日志等有限集合。`.github/actions/`、图片、requirements、构建脚本仍是 unknown，不能用宽泛 glob 隐藏。这里的 ignore 表示“本次文件影响映射不参与目标语义”，不表示文件可信。

## fsck 实测与 W3-D 仓库规模

[原始 JSON](results/w3b-v1/fsck-benchmark.json) 使用与 W3-A 相同的 `fsck --full --strict --no-reflogs --no-dangling <base> <head>`，在 Windows 11、Git 2.53.0.windows.2 上各跑 5 次：

| 可达对象 | loose 最大耗时 | packed 最大耗时 | 是否触及 5 秒 |
|---:|---:|---:|---|
| 1,003 | 493.51 ms | 256.69 ms | 否 |
| 5,003 | 1,276.50 ms | 190.10 ms | 否 |
| 10,003 | 2,112.88 ms | 178.24 ms | 否 |
| 16,003 | 2,088.14 ms | 130.60 ms | 否 |

当前仓库为 838 个 loose 对象，最大 391.21 ms。**本机没有测到“多少对象必然接近 5 秒”的阈值**；同样对象数在 loose/packed 下相差一个数量级，缓存、对象大小和文件系统也会改变结果，不能把对象数拟合成通用承诺。W3-D 不选 pandas 量级仓库；首个试点限定为存储不超过 64 MiB、loose 元数据不超过 10,000 项，并要求在实际机器按同命令预跑 5 次、最大值不超过 2.5 秒。packed 仓库也必须预跑，不能因目录项少就跳过。超出该准入返回 unknown 或更换更小试点，不提高 5 秒标准。

## W3-B Docker 固定策略

`docker-policy.v1` 的字段均为 Literal 常量，不接收项目配置覆盖：network/ipc none、只读根文件系统与工作区 bind、UID/GID 65532、drop ALL capabilities、no-new-privileges、64 PID、256 MiB 内存且不使用额外 swap、1 CPU、64 MiB `/tmp` tmpfs、30 秒测试上限，以及 stdout/stderr/JUnit/传输上限。镜像必须按本地 `sha256:` image ID 存在，运行使用 `--pull=never`；未传宿主环境、凭据、Docker socket或其他宿主目录。

工作区 bind 的宿主来源不是仓库根，而是本次运行中新建的最小目录；它只含授权 pin 的 source/contract/dependency 和 Guard test，并在复制时再次核对摘要。未声明文件、项目配置、`.git`、`conftest.py` 和 `pytest.ini` 不进入 mount；因此它们不只是在 pytest 参数层被忽略，而是在文件系统层不可见。

容器 entrypoint 只接受严格 base64 JSON manifest，自建空 pytest.ini，保持插件自动发现关闭，使用 `--noconftest -p no:cacheprovider --capture=no`，并以进程组终止超时/日志洪泛。Docker PID 1 退出后容器删除；宿主还有独立墙钟与传输上限并尝试 `docker rm -f`。真实 fixture 已在 WSL2/Linux engine 上读取 `/proc` 和 cgroup 值，验证非 root、只读写边界、无网络、CapEff=0、NoNewPrivs=1、CPU/内存/PID限制、宿主秘密不在环境、恶意 conftest/pytest.ini 不加载、超时子孙清理和日志洪泛不成为 pass。详见 [W3-B 记录](progress/w3b.md)。

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
| W01 | 最小输入挂载、文件/网络、CPU/内存/PID、子孙进程隔离 | [正式 runner 四项原 fixture](progress/w3b-formal.md) | 已测，正式镜像与字节锁定/恢复通过；非通用内核/daemon 安全证明 |
| W03 | 插件/conftest、安装/build hooks、声明配置 | 正式受控执行；[完整提交树预检](preflight.md) | 受控模式已测；validators 的配置、目标/契约不兼容而阻断；显式插件模式未实现 |
| W04 | Registry 状态/完整性，CI 权限/公开日志 | [本地 Registry 专项与真实 CLI](progress/w3c.md) | 本地子项已测；身份角色、签名/防回滚、生命周期、CI 和公开日志继续开放 |

## 剩余风险与准入

只读检查仍调用宿主可信 Git 的原生解析器。限额不是 OS 内存沙箱，也不能在阻塞文件系统调用或清理阶段保证严格墙钟上限；未证明抗 Git 压缩数据内存耗尽、Git 自身漏洞或任意后台子孙进程。未做全面 fuzz、全部平台/编码/文件系统矩阵。

路径/元数据检查不是 OS 原子快照；引用变化检测不证明抵抗恶意替换并恢复、权限攻击或全部 TOCTOU。摘要和 fsck 不认证作者/仓库身份，也不消除 SHA-1 与工具链的信任假设。

W3-B 的 Docker 限制保护宿主，不证明容器内被测代码诚实。目标与 pytest 位于同一解释器，恶意目标可能干扰 pytest/JUnit；严格 envelope 和宿主重建能防止畸形/超限输出被当成通过，却不是远程证明或独立 oracle。Docker daemon、WSL2/内核、runner 基础镜像和宿主控制面仍是可信计算基。Git 检查仍在宿主受限进程中执行，没有迁入容器。

W3-B 正式镜像和 W3-C 的前置准入已通过；[validators](progress/w3d.md) 仍因自身配置/契约/Guard/Scope 缺口停止在执行前，unknown 不算执行试点成功。正式 runner 以后重建必须新锁新验收，tag 不能替代 image ID。W4 继续关闭权限/签名/CI 等剩余项；Docker 不可用或检查失败时，不以本地执行器替代。
