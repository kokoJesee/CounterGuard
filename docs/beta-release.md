# CounterGuard 0.5.0 Beta

本版把受限的首次接入串联为：准备 H 内契约 → Docker 双向 Evidence → 最小 Guard 自检 →
精确闭包快照 Scope → Candidate → 人工审核 Shadow → 统一 verify。
具体命令见[首次接入](onboarding.md)和[最小 Guard](standalone-guards.md)。

Beta 支持 Python 普通模块/包、根或 src 布局、零运行时依赖和受限字面量 oracle。
已有冻结 scope_v1 的数据、标签、算法及指标保持原样；没有把小样本学习结论自动扩展到新项目。
新源码快照、未知依赖或未支持 oracle 仍返回 unknown，不会为了接入成功放宽安全边界。

## 公开发布的范围

[v0.5.0](https://github.com/kokoJesee/CounterGuard/releases/tag/v0.5.0) 已创建为 GitHub Release（prerelease、非草稿），
包含发行说明、wheel、sdist、base/runner 两份哈希依赖清单、已审核 root runner 归档和 SHA256SUMS，共 6 个附件。
发布时的独立读回见[交付收据](results/beta-v0.5.0/delivery.json)；[后续复核](results/boltons-standalone-retrial-v1/README.md)再次核对了大小与摘要。
本项目尚未向 PyPI 发布；“GitHub Beta 已发布”只说明上述 GitHub 交付，不表示 PyPI、托管 CI 或任意项目兼容已验收。

## 安装

GitHub 发布材料使用 counterguard-0.5.0 wheel/sdist、带哈希的基础/runner 依赖清单及已审核 root runner 归档。
发布是否完成、文件摘要及本次实际验证结果以发布页和同版验收记录为准；本页不表示某次未完成的检查已通过。
不在 PyPI 发布同名包，也不把旧的本地 v0.1.0 标签改作 Beta。

从 [v0.5.0 Release](https://github.com/kokoJesee/CounterGuard/releases/tag/v0.5.0)
下载 wheel、需要的依赖清单、源码包与 SHA256SUMS，逐项核对摘要后，在新虚拟环境安装。
例如要运行可信 Demo，使用 runner 清单；只用静态 CLI 时可选 base 清单。

```powershell
python -m venv .venv
# 先将 Get-FileHash 的结果与 SHA256SUMS 对照；下列安装不代替摘要核对。
Get-FileHash counterguard-0.5.0-py3-none-any.whl -Algorithm SHA256
.venv/Scripts/python -m pip install --only-binary=:all: --require-hashes -r counterguard-0.5.0-runner-requirements.txt
.venv/Scripts/python -m pip install --no-deps counterguard-0.5.0-py3-none-any.whl
# 解开源码包，把短路径 <source-root> 指向其中的 counterguard-0.5.0。
.venv/Scripts/python -I -m counterguard demo --cwd <source-root> --workspace a/demo
.venv/Scripts/python -I -m counterguard demo --cwd <source-root> --workspace a/demo --verify-only
```

Linux/macOS 使用 `.venv/bin/python`。Demo 的仓库根输入必须来自解开的同版源码包；
受审 runner 归档则用于真实仓库的 Docker 捕获/重放，可信本地 Demo 不消费该归档。

```powershell
# 在源码分发/仓库中运行；不安装任意目标项目。
uv sync --frozen
uv run counterguard version
uv run counterguard runner list

# 构建自己的候选包时使用新目录；这不会自动审核新构建的 Docker 镜像。
uv build --out-dir dist/beta-build-v1
python -m pip install "dist/beta-build-v1/counterguard-0.5.0-py3-none-any.whl[runner]"
```

基础 wheel 提供 CLI 和类型模型；Demo 在缺 pytest 时返回 3，说明安装 counterguard[runner]，不启动执行或创建输出。
runner extra 供可信本地 Demo 使用；仓库目标仍只有专用 Docker 路径。
Demo 还需要 sdist 中的 examples、benchmarks、experiments 和 tests/contract_tests，不在 wheel 内偷偷寻找当前 checkout。

严格的验收安装先核对 wheel 和依赖清单的 SHA-256，再用
`pip install --only-binary=:all: --require-hashes -r <reviewed-requirements.txt>` 安装锁定的工具依赖，
最后安装已核对的 wheel。两份清单在 [requirements/](../requirements/)，由现有 uv.lock 导出，没有增加运行时依赖。
这些是工具的可信安装材料，不是给任意目标仓库开放依赖安装。

## 已审核 Docker 镜像

核对归档 SHA-256 后再 docker load，之后运行 `counterguard runner show root-pytest8` 检查审核链与本机 availability。
归档提供既有 image ID 的精确字节；浮动 tag、重新构建后看起来相同的镜像和自己改写的 catalog 都不能替代它。
自己重建的新 image ID 需要另行审核与新目录收据。

Beta 的[可复制 workflow](../examples/github-actions/counterguard-beta.yml)固定工具提交、wheel/依赖清单/归档摘要；
哈希不匹配、下载缺失或 Docker 不可用就失败，没有绿色 skip 或本地回退。
模板仅提供人工触发的工具自有示例，不是自动执行任意 PR 的服务。
本地驱动实测和模板结构检查不能冒充 GitHub 托管平台的真实运行记录，详见 [CI 文档](github-actions.md)。

## 干净环境验收与 Windows 路径

从 checkout 外新建基础和 runner 两个环境，使用 Python `-I`，核对 `counterguard.__file__` 在新环境 site-packages，
并比较安装包源码摘要。必须实际运行完整 Demo、独立复验、真实仓库示例与 CI 驱动，不能用 help 成功替代。
真实进程测试为 slow；开发过程跑快速层和专项，发布检查点再跑一次全量和各审核镜像的四项攻击。

Windows 应使用短的源码输入根目录和输出名。240 UTF-16 单位的预防门限保留，超过时会在执行前拒绝；
不要删除门限或给旧失败目录补签成功。首次深目录安装验收确实触发过此拒绝，原始记录保留后改用新的短目录。
失败重试的来源、原因和最终结果分别记录，不把最初失败从计时或报告中移除。
来源链会反复从原始事实重建，本机集成验收已有明显耗时；实际全量时间见同版收据。
当前没有秒级 verify 或任意项目 30 分钟完成接入的承诺，性能优化也不能省略执行前后的来源/状态复核。

## 许可、隐私与范围

项目及 wheel 元数据为 [Apache-2.0](../LICENSE)，validators 来源为 [MIT](../integrations/pilot/LICENSE.validators.txt)。
Docker 基础发行版、Python 和工具依赖保留各自许可；工具项目许可不替代这些第三方许可。
原始日志、Registry、绝对路径、操作者标签与含个人身份元数据的本机 Git bundle 不随发布材料上传。
状态和来源摘要不提供签名、所有者身份认证或对恶意目标伪造 JUnit 的证明。

不包含 Dashboard、云服务、远程 Registry、GitHub App、MCP、多语言、任意原生 pytest/插件引导、目标依赖安装或自动提升 Active。
本机精确快照 Registry 不可直接搬到 CI 改签；外部贡献的远程权限与可携带来源交付仍需另行设计。
真实 validators 记录是固定 B/F/H MAC 试点，owner H 和原始 bundle 仍受本机交付/隐私限制，不能声称全新机器已自动接入该仓库。
