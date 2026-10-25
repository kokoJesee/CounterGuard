# CounterGuard 0.5.0 Beta

这一版把受限的首次接入串成一条链：准备 H 内契约 → Docker 双向 Evidence → 最小 Guard 自检 → 精确闭包快照 Scope → Candidate → 人工审核进入 Shadow → 统一 verify。具体命令见[首次接入](onboarding.md)和[独立 Guard](standalone-guards.md)。

支持范围是 Python 普通模块和包、根目录或 `src/` 布局、零运行时依赖，以及受限的字面量 oracle。冻结 scope_v1 的数据、标签、算法和指标保持原样，也没有把小样本的学习结论自动扩展到新项目。新源码快照、未知依赖或未支持的 oracle 仍然返回 unknown，不会为了接入成功去放宽安全边界。

## 发布内容

[v0.5.0](https://github.com/kokoJesee/CounterGuard/releases/tag/v0.5.0) 是 GitHub prerelease，包含发行说明、wheel、sdist、base/runner 两份带哈希的依赖清单、已审核的 root runner 归档和 SHA256SUMS，共 6 个附件。

发布时的独立读回见[交付收据](results/beta-v0.5.0/delivery.json)，后续复核也再次核对了大小和摘要。项目没有向 PyPI 发布任何同名包；「GitHub Beta 已发布」只说明上面这些交付物，不代表 PyPI、托管 CI 或任意项目兼容已经验收。

## 安装

从 Release 下载 wheel、对应的依赖清单、源码包和 SHA256SUMS，逐项核对摘要后装进新的虚拟环境。要运行可信 Demo，用 runner 清单；只用静态 CLI，用 base 清单。

```powershell
python -m venv .venv
# 先把 Get-FileHash 的结果和 SHA256SUMS 对照；下面的安装不能代替摘要核对。
Get-FileHash counterguard-0.5.0-py3-none-any.whl -Algorithm SHA256
.venv/Scripts/python -m pip install --only-binary=:all: --require-hashes -r counterguard-0.5.0-runner-requirements.txt
.venv/Scripts/python -m pip install --no-deps counterguard-0.5.0-py3-none-any.whl
# 解开源码包，把短路径 <source-root> 指向其中的 counterguard-0.5.0。
.venv/Scripts/python -I -m counterguard demo --cwd <source-root> --workspace a/demo
.venv/Scripts/python -I -m counterguard demo --cwd <source-root> --workspace a/demo --verify-only
```

Linux 和 macOS 用 `.venv/bin/python`。Demo 的仓库根输入必须来自解开的同版源码包；受审的 runner 归档只用于真实仓库的 Docker 捕获和重放，可信本地 Demo 不消费它。

从源码分发安装也可以：

```powershell
# 在源码分发或仓库里运行，不安装任意目标项目。
uv sync --frozen
uv run counterguard version
uv run counterguard runner list

# 构建自己的候选包时用新目录；这不会自动审核新构建的 Docker 镜像。
uv build --out-dir dist/beta-build-v1
python -m pip install "dist/beta-build-v1/counterguard-0.5.0-py3-none-any.whl[runner]"
```

基础 wheel 提供 CLI 和类型模型。缺 pytest 时 Demo 返回 3，提示安装 `counterguard[runner]`，不会启动执行或创建输出。runner extra 供本地 Demo 使用；仓库目标仍然只能走专用 Docker 路径。

Demo 还需要 sdist 里的 `examples`、`benchmarks`、`experiments` 和 `tests/contract_tests`，不会去当前 checkout 里偷偷找。

严格的验收安装要先核对 wheel 和依赖清单的 SHA-256，再用 `pip install --only-binary=:all: --require-hashes -r <reviewed-requirements.txt>` 装锁定依赖，最后安装已核对的 wheel。两份清单在 [requirements/](../requirements/)，由现有 `uv.lock` 导出，没有增加运行时依赖。这些是工具自己的可信安装材料，不是给任意目标仓库开放依赖安装。

## 已审核 Docker 镜像

核对归档 SHA-256 后再 `docker load`，然后用 `counterguard runner show root-pytest8` 检查审核链和本机 availability。

归档提供的是既有 image ID 的精确字节。浮动 tag、重新构建后看起来相同的镜像、自己改写的 catalog，都不能替代它。自己重建的新 image ID 需要另行审核和新的目录收据。

Beta 的[可复制 workflow](../examples/github-actions/counterguard-beta.yml)固定了工具提交，以及 wheel、依赖清单和归档的摘要。哈希不匹配、下载缺失或 Docker 不可用都会失败，没有绿色 skip，也没有本地回退。这个模板只是人工触发的工具自有示例，不是自动执行任意 PR 的服务。本地驱动实测和模板结构检查，不能冒充 GitHub 托管平台上的真实运行记录，详见 [CI 文档](github-actions.md)。

## 干净环境验收与 Windows 路径

从 checkout 之外新建 base 和 runner 两个环境，使用 Python `-I`，确认 `counterguard.__file__` 指向新环境的 site-packages，再比较安装包源码摘要。

必须实际跑完整 Demo、独立复验、真实仓库示例和 CI 驱动，不能用 `--help` 成功代替。真实进程测试标为 slow；开发过程跑快速层和专项，发布检查点再跑一次全量，以及各审核镜像的四项攻击。

Windows 上要用短的源码输入根目录和输出名。240 UTF-16 单位的预防门限保留，超过时在执行前拒绝。不要删门限，也不要给旧失败目录补签成功。首次深目录安装验收确实触发过这个拒绝，原始记录保留后改用了新的短目录。

失败重试的来源、原因和最终结果分别记录，不把最初失败从计时或报告里移除。来源链会反复从原始事实重建，本机集成验收已有明显耗时，实际全量时间见同版收据。当前没有秒级 verify，也没有「任意项目 30 分钟接入」的承诺；性能优化同样不能省掉执行前后的来源和状态复核。

## 许可、隐私与范围

项目及 wheel 元数据是 [Apache-2.0](../LICENSE)，validators 来源是 [MIT](../integrations/pilot/LICENSE.validators.txt)。Docker 基础发行版、Python 和工具依赖保留各自的许可，工具项目的许可不替代这些第三方许可。

原始日志、Registry、绝对路径、操作者标签，以及含个人身份元数据的本机 Git bundle，都不随发布材料上传。状态和来源摘要不提供签名、所有者身份认证，也不能证明恶意目标没有伪造 JUnit。

本版不包含 Dashboard、云服务、远程 Registry、GitHub App、MCP、多语言、任意原生 pytest/插件引导、目标依赖安装，也不自动提升 Active。本机精确快照 Registry 不能直接搬到 CI 改签；外部贡献的远程权限和可携带来源交付仍需另行设计。真实 validators 记录是固定 B/F/H 的 MAC 试点，owner H 和原始 bundle 仍受本机交付与隐私限制，不能声称一台全新机器已经自动接入了该仓库。
