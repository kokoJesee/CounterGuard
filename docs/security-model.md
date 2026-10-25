# 安全模型与准入记录

这一页记录 CounterGuard 自己的安全边界：信任什么、控制什么、哪些风险还没关。它不是通用沙箱，也不是安全认证。只读检查、独立授权与受限执行、本地 Registry 都有记录，validators 的固定 manifest-v5 试点也已完成；镜像字节锁定和四项攻击结果见[验收记录](results/w3b-formal-v1/runner-receipt.json)与[攻击面清单](attack-surface-checklist.md)。

## 资产与信任

可信的：本机 Python、Pydantic、Git 可执行文件、调用者的 PATH 和 OS、工具源码，以及工作区权限。不可信的：仓库里的 Python、Git 配置和 hooks、路径、引用、对象数据，以及可能来自仓库的项目配置。显式选择一份配置文件，不等于它已经过语义审核。

要保护的是宿主文件和凭据、历史产物、冻结数据、来源关联，以及「未执行」这个语义。只读检查只产生改动候选：`InspectionReport` 和 `TargetImpact` 的 Schema 把 `execution_allowed` 定义为 `const false`，代码里没有把它置真的路径，ready 也不会翻转开关。

Docker 执行使用另一份 `docker-execution-authorization.v1`。只有可信宿主控制面调用 `authorize_docker_execution` 时才产生一次请求绑定，而且要同时满足这些条件：当前检查器源码、Inspection 自摘要、配置原字节、ready/affected 且没有不确定项、head 的 Git 与内容 pin、物化工作区、Guard 测试、精确 replay 请求、固定 Docker policy，以及本地镜像 ID。配置还必须显式声明由 `source_ref` 唯一推导出的 Python `module`，避免执行时导入另一个可见模块。DockerExecutor 启动前和退出后都会从这些可信来源重建授权，只重算 JSON 自摘要不够。仓库配置、被测 Python 和 Inspection 本身都不能授权；Docker 不可用或镜像身份不符时，也不会回退到 `LocalTrustedExecutor`。

这里的「可信宿主控制面」是进程内信任假设：当前库函数没有身份角色或签名认证。本地 Registry 保存登记和禁用事实、重验来源，但不认证操作者。限制授权调用者、补齐身份、签名和 CI 权限仍未完成，不能把任何拥有宿主 Python 执行权的调用者当成已鉴权。

## 只读仓库检查的控制

1. 校验根路径和配置的既有组成部分，拒绝 symlink 与 Windows reparse point。只读普通 `.git` 目录；gitfile、worktree/commondir、reftable 等布局返回 unknown，不跟随外部 gitdir。
2. 受限读取 HEAD、heads/tags、packed-refs 和 shallow。对象目录会预查链接、特殊文件、alternates 和体积；不读原仓库的 config、hooks、index 或 reflog。
3. 临时裸 Git 元数据由工具生成，只复制校验后的引用和 shallow。通过显式对象目录读原对象，cwd 不在被检仓库里。关闭全局与系统配置，不继承 `GIT_*` 环境，关闭 replace、延迟获取、协议、可选锁和 fsmonitor。
4. 只运行 `version`、`rev-parse`、`fsck`、`diff-tree`、`ls-tree`、`cat-file`。修订受限并使用 `--end-of-options`；路径是 literal pathspec；diff 禁用 external diff/textconv 和 rename 猜测，重命名按 D+A 处理。
5. `fsck` 检查对象完整性；读取映射文件后再核对 blob 的 Git ID 和长度，保存内容 SHA-256。提交和原始字节是事实来源，不使用 dirty working tree。Git symlink 拒绝，gitlink 和子模块 unknown，不初始化。
6. 再读一次引用快照，变化时返回 unknown。输出使用固定原因码，不回显 Git stderr、绝对仓库路径或源码正文。绑定配置字节、选定提交、文件对象/内容与包源码摘要，不虚构时间。

选项依据 [Git 环境说明](https://git-scm.com/docs/git)、[修订校验](https://git-scm.com/docs/git-rev-parse)、[raw diff / 过滤器](https://git-scm.com/docs/git-diff-tree)和 [fsck](https://git-scm.com/docs/git-fsck)；不启用会写 lost-found 的选项。实际覆盖以本项目测试为准，不能从选项名称推断安全。

## 资源限额

| 项目 | 限额 / 规则 |
|---|---|
| 配置 | JSON 子集，128 KiB；128 个目标，每个目标最多 64 个显式依赖 |
| 路径 | 512 字符，NFC、相对 POSIX；拒绝控制字符、格式字符、ADS、盘符、Windows 非法/保留名和遍历 |
| 元数据 | 每次目录遍历 16384 项；合成引用 2048；只支持普通 SHA-1、ASCII heads/tags 与 HEAD/祖先语法 |
| 对象 | 存储文件合计 128 MiB；映射文件单个 1 MiB、累计读取 8 MiB |
| Git 输出与时间 | 单次 stdout 2 MiB、stderr 64 KiB；单进程 5 秒，启动前核对 30 秒检查预算；超限 unknown |
| 影响范围 | 精确的 source/contract/dependency refs；`ignored_paths` 必须逐路径声明，且只接受文档、根级许可证/变更日志/仓库元数据和少量 CI 控制文件；其他未映射改动 unknown |

ready 只代表指定提交可读、声明的映射覆盖当前改动。它不证明符号存在、契约业务语义、配置受信、依赖完整或 Guard 适用；unaffected 也不是 Scope 的 inapplicable。删除或缺失 head 输入返回 unknown；新目标和契约仍然要人工审核与真实验证。

一个 PR 同时改了源码和 `.github/workflows/ci.yml` 时，只有配置把这个精确路径放进 `ignored_paths`，才会得到 affected/ready；没有声明就是 unknown。允许声明的是直接位于 `.github/workflows/` 下的 yml/yaml、`.github/dependabot.yml|yaml`、`.circleci/config.yml`、根级 `.gitignore`/CI 元数据，以及文档、许可证、变更日志这类有限集合。`.github/actions/`、图片、requirements 和构建脚本仍是 unknown，不能用宽泛 glob 藏起来。这里的 ignore 表示「这次文件影响映射不参与目标语义」，不表示文件可信。

## fsck 实测与仓库规模

[原始 JSON](results/w3b-v1/fsck-benchmark.json) 用的是与只读检查相同的 `fsck --full --strict --no-reflogs --no-dangling <base> <head>`，在 Windows 11、Git 2.53.0.windows.2 上各跑 5 次：

| 可达对象 | loose 最大耗时 | packed 最大耗时 | 是否触及 5 秒 |
|---:|---:|---:|---|
| 1,003 | 493.51 ms | 256.69 ms | 否 |
| 5,003 | 1,276.50 ms | 190.10 ms | 否 |
| 10,003 | 2,112.88 ms | 178.24 ms | 否 |
| 16,003 | 2,088.14 ms | 130.60 ms | 否 |

当前仓库有 838 个 loose 对象，最大 391.21 ms。本机没有测到「多少对象必然接近 5 秒」的阈值；同样对象数在 loose 和 packed 下差一个数量级，缓存、对象大小和文件系统也会改变结果，不能把对象数拟合成通用承诺。

因此试点不选 pandas 量级的仓库。首个试点限定存储不超过 64 MiB、loose 元数据不超过 10,000 项，并要求在实际机器上用同一条命令预跑 5 次、最大值不超过 2.5 秒。packed 仓库也要预跑，不能因为目录项少就跳过。超出这个准入范围就返回 unknown 或换更小的试点，不提高 5 秒标准。

## Docker 固定策略

`docker-policy.v1` 的字段都是 Literal 常量，不接受项目配置覆盖：network/ipc 为 none，只读根文件系统，工作区 bind，UID/GID 65532，drop ALL capabilities，no-new-privileges，64 个 PID，256 MiB 内存且不加额外 swap，1 CPU，`/tmp` 64 MiB tmpfs，测试上限 30 秒，以及 stdout/stderr/JUnit/传输上限。镜像必须按本地 `sha256:` image ID 存在，运行时 `--pull=never`；不传宿主环境、凭据、Docker socket 或其他宿主目录。

工作区 bind 的宿主来源不是仓库根，而是本次运行新建的最小目录。目录里只有授权 pin 的 source/contract/dependency 和 Guard 测试，复制时还会再核对一次摘要。未声明文件、项目配置、`.git`、`conftest.py` 和 `pytest.ini` 都不进 mount，所以在文件系统层就不可见，不只是被 pytest 参数忽略。

容器 entrypoint 只接受严格 base64 JSON manifest，自建空的 pytest.ini，关闭插件自动发现，使用 `--noconftest -p no:cacheprovider --capture=no`，并在超时或日志洪泛时终止整个进程组。PID 1 退出后删除容器；宿主还有独立的墙钟和传输上限，并会尝试 `docker rm -f`。真实 fixture 已在 WSL2/Linux engine 上读取 `/proc` 和 cgroup：验证了非 root、只读写边界、无网络、`CapEff=0`、`NoNewPrivs=1`、CPU/内存/PID 限制、宿主秘密不在环境、恶意 conftest/pytest.ini 不加载、超时子孙进程被清理，以及日志洪泛不会变成 pass。详见 [Docker 测试记录](results/w3b-v1/docker-tests.txt)。

不支持的合法布局或格式、缺失历史，返回 unknown；越界、链接、损坏对象直接拒绝（退出 5），不自动修复、不拉取、不回退到全仓执行。过大的仓库或过不了 strict fsck 的旧对象也可能被保守拒绝；这里不宣称支持所有 Git 仓库。

## 攻击 fixture 与已测范围

| ID | 攻击 / 缺口 | 实现与测试 | 当前结论 |
|---|---|---|---|
| W02-A | 参数、路径、YAML / 可执行配置、未映射改动 | project_config / change_analysis；test_project_config.py、test_change_analysis.py | 拒绝或 unknown，不产生执行许可 |
| W02-B | 原配置、环境、hooks、fsmonitor / 过滤器 | repository；test_repository.py 里的无效 config、恶意 helper、`GIT_*` 注入 | 不读原 config，marker 未生成 |
| W02-C | gitfile、alternates、junction/reparse、Git symlink、gitlink | test_repository.py 的真实 Git / Windows junction | 拒绝或 unsupported unknown，不跟随、不初始化 |
| W02-D | 缺提交、浅克隆、packed refs、损坏对象、引用变化 | test_repository.py | 不补历史、不联网；损坏拒绝、变化 unknown |
| W02-E | 输出/时间超额、含凭据的 stderr | test_repository_limits.py 的外部进程故障注入 | 固定原因码；不是实际恶意 Git fuzz |
| W02-F | dirty tree、重复读、三种格式 | 真实 CLI；[只读检查验收](results/w3a-v1/acceptance.json) | 仓库字节和 mtime 不变，未导入目标 |
| W01 | 最小输入挂载、文件/网络、CPU/内存/PID、子孙进程隔离 | [正式 runner 四项原 fixture](results/w3b-formal-v1/docker-tests.txt) | 已测，正式镜像与字节锁定/恢复通过；不是通用内核或 daemon 安全证明 |
| W03 | 插件/conftest、安装/build hooks、声明配置 | [完整提交树预检](preflight.md)；[validators 固定 pilot](results/w3d-fork-v1/final-acceptance.json) | 固定 MAC pilot 已测；任意插件、fixture、安装模式和仓库语义仍需独立审核，通用自动准入未实现 |
| W04 | Registry 状态/完整性、CI 权限/公开日志 | [本地 Registry](registry.md) 与真实 CLI | 本地 Registry 与生命周期子项已测；身份角色、签名/防回滚、CI 和公开日志仍开放 |

## 剩余风险

只读检查仍然调用宿主可信 Git 的原生解析器。限额不是 OS 内存沙箱，也不能在阻塞文件系统调用或清理阶段保证严格墙钟上限；还没有证明能抵抗 Git 压缩数据的内存耗尽、Git 自身漏洞或任意后台子孙进程，也没做全面 fuzz 和全平台/编码/文件系统矩阵。

路径和元数据检查不是 OS 原子快照；引用变化检测不证明能抵抗「恶意替换后再恢复」、权限攻击或全部 TOCTOU。摘要和 fsck 不认证作者或仓库身份，也不消除 SHA-1 与工具链的信任假设。

Docker 限制保护的是宿主，不证明容器里的被测代码诚实。目标和 pytest 在同一个解释器里，恶意目标可能干扰 pytest/JUnit；严格 envelope 和宿主重建能防止畸形或超限输出被当成通过，但不是远程证明或独立 oracle。Docker daemon、WSL2/内核、runner 基础镜像和宿主控制面仍然是可信计算基。Git 检查仍在宿主受限进程中执行，没有迁进容器。

validators 的固定 manifest-v5 试点已经在 Docker 中通过，最终记录限定为 B/F/H 的 MAC 10-case 快照，并确认没有学习 Scope，也没有本地执行回退，见[最终验收](results/w3d-fork-v1/final-acceptance.json)。这不代表任意仓库都能准入。正式 runner 以后重建必须重新锁定、重新验收，tag 不能替代 image ID。权限、签名、CI 等剩余项仍在关闭中；Docker 不可用或检查失败时，不会用本地执行器替代。
