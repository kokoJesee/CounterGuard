# pytest 执行策略

日期：2026-10-14。当前实现覆盖可信本地样本；真实仓库配置接入归 Week 3。

## 三个追问的处理

### 1. 插件自动加载与 conftest

`PYTEST_DISABLE_PLUGIN_AUTOLOAD=1` 是长期默认策略：执行只依赖明确声明的插件，避免本机安装了什么就自动参与验证。它只关闭已安装插件 entry point 的自动发现，不会关闭 conftest 加载，也不会阻止显式 `-p` / `pytest_plugins`。参见 [pytest 插件加载规则](https://docs.pytest.org/en/stable/how-to/writing_plugins.html) 与 [显式插件加载](https://docs.pytest.org/en/stable/how-to/plugins.html)。

本轮的受控执行器进一步使用 `--noconftest` 和独立空 `pytest.ini`，不沿用仓库的 addopts、required_plugins 或 conftest。环境中的 PYTEST_ADDOPTS / PYTEST_PLUGINS 不传入子进程。测试已放置会报错的 conftest 和指向不存在插件的仓库配置，确认它们不影响受控运行。

Week 3 的真实仓库接入将新增独立的项目执行模式，仍保留自动加载关闭，但允许显式声明插件和 fixture 引导方式：

| 配置项 | 规则 |
|---|---|
| pytest 配置文件 | 显式指定并记录内容摘要 |
| 第三方插件 | 显式 `-p`，锁定包版本和加载清单 |
| conftest / fixture 引导模块 | 明确选择允许的目录或模块，记录摘要，并在 Docker 内执行 |
| 其他隐式依赖 | 不自动补齐；缺失时产生执行错误及说明 |

独立 Guard 位于 artifacts 下，不会天然继承 `tests/conftest.py` 中的 fixtures。需要这些 fixtures 的项目必须声明引导方式并通过接入测试；当前纯 JSON 函数契约不能承诺覆盖所有框架测试。Week 3 验收要求包括：必要插件/fixture 成功加载、未声明依赖明确失败、固定配置可重复执行、配置或插件版本变化改变执行清单。

这些选项管理加载行为。未知仓库代码的执行隔离由 Week 3 Docker backend 提供。

### 2. raises 白名单

已移除 `getattr(builtins, name)`。契约验证、样本测试和 Guard Schema 使用明确的三种异常：`ValueError`、`TypeError`、`OverflowError`。名字不在名单中立即拒绝，不尝试动态导入；SystemExit、KeyboardInterrupt、Exception、str 等不能混入。

生成的独立 pytest 文件内嵌相同的异常映射，不依赖源契约或源码包中的异常解析函数。扩展白名单需要同步 Schema 与生成器，并新增回归样本。用户自定义异常将在后续契约版本中显式声明和解析，当前没有默认开放。

### 3. python -m evidenceguard

缺少 `__main__.py` 是遗漏，现已补齐。它与 console script 都调用 `evidenceguard.cli.app`。模块入口已实际验证 version 和 Guard 重放，不存在另一套参数或退出码逻辑。
