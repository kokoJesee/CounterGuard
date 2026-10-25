# pytest 执行策略

可信本地样本继续使用 LocalTrustedExecutor；未知仓库走 Docker 受控模式。

## 三个追问的处理

### 1. 插件自动加载与 conftest

`PYTEST_DISABLE_PLUGIN_AUTOLOAD=1` 是长期默认策略：执行只依赖明确声明的插件，避免本机安装了什么就自动参与验证。它只关闭已安装插件 entry point 的自动发现，不会关闭 conftest 加载，也不会阻止显式 `-p` / `pytest_plugins`。参见 [pytest 插件加载规则](https://docs.pytest.org/en/stable/how-to/writing_plugins.html) 与 [显式插件加载](https://docs.pytest.org/en/stable/how-to/plugins.html)。

本轮的受控执行器进一步使用 `--noconftest` 和独立空 `pytest.ini`，不沿用仓库的 addopts、required_plugins 或 conftest。环境中的 PYTEST_ADDOPTS / PYTEST_PLUGINS 不传入子进程。测试已放置会报错的 conftest 和指向不存在插件的仓库配置，确认它们不影响受控运行。

需要第三方插件/fixture 的项目最终需要独立显式模式，仍保留自动加载关闭，并固定以下来源：

| 配置项 | 规则 |
|---|---|
| pytest 配置文件 | 显式指定并记录内容摘要 |
| 第三方插件 | 显式 `-p`，锁定包版本和加载清单 |
| conftest / fixture 引导模块 | 明确选择允许的目录或模块，记录摘要，并在 Docker 内执行 |
| 其他隐式依赖 | 不自动补齐；缺失时产生执行错误及说明 |

独立 Guard 位于 artifacts 下，不会天然继承 `tests/conftest.py` 里的 fixtures。这一版选择更窄的安全边界：只提供受控模式，使用空配置、`--noconftest`、`-p no:cacheprovider` 和禁自动插件，不在宿主或容器里安装项目。

会依赖项目 conftest、插件、build hook 或安装步骤的仓库，不进入首个试点，而不是自动补齐后继续执行。

显式插件模式尚未实现。以后实现时，配置/插件包/fixture 引导模块必须进入授权摘要与 runner 镜像构建记录，并用新的 policy/配置协议版本；不能扩大 docker-policy.v1 的含义。

这些选项管理加载行为。Docker backend 另提供宿主隔离；它们共同生效，任一失败都不回退到本地 pytest。

### 2. raises 白名单

已移除 `getattr(builtins, name)`。契约验证、样本测试和 Guard Schema 使用明确的三种异常：`ValueError`、`TypeError`、`OverflowError`。名字不在名单中立即拒绝，不尝试动态导入；SystemExit、KeyboardInterrupt、Exception、str 等不能混入。

生成的独立 pytest 文件内嵌相同的异常映射，不依赖源契约或源码包中的异常解析函数。扩展白名单需要同步 Schema 与生成器，并新增回归样本。用户自定义异常将在后续契约版本中显式声明和解析，当前没有默认开放。

### 3. python -m counterguard

缺少 `__main__.py` 是遗漏，现已补齐。它与 console script 都调用 `counterguard.cli.app`。模块入口已实际验证 version 和 Guard 重放，不存在另一套参数或退出码逻辑。
