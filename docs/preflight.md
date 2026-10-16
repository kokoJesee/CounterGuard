# 候选仓库的只读执行预检

```powershell
uv run evidenceguard preflight --repo artifacts/pilot/validators-discovery-v1/repo --revision 6ffd8625ee4272dade063653bff615014bdc4734
```

预检只读取完整 Git 提交树，不 checkout、不安装、不加载 conftest、不 import 目标或执行 Python。复用 W3-A 的对象/路径/fsck 安全 profile；最多 2048 个文件、单文件 1 MiB、总原始文件 8 MiB。结果列出每个文件的 Git/内容 pin 与实际实现摘要，重复同输入逐字节一致，不伪造执行时间。工作树删改不隐藏提交里的要求。

检查包括：嵌套 conftest、AST 中的 pytest_plugins、pyproject 的 runtime/dynamic/optional dependencies、setup/legacy pytest 配置、`required_plugins` / `-p`、最小 pytest 版本、导入根、源文件能否静态解析。支持 `tool.pytest.ini_options` 和 pytest 9 的 `tool.pytest`，以及 `pytest.toml` / `.pytest.toml`；不能只搜索四个传统文件名。格式依据 [pytest 官方配置文档](https://docs.pytest.org/en/9.0.x/reference/customize.html)。

| 结果 | 退出码 | 含义 |
|---|---:|---|
| eligible_candidate | 0 | 静态未发现当前 profile 的已知阻塞；仍不是执行许可或依赖完整性证明 |
| blocked / unknown | 4 | 已知不兼容 / 信息不够；列 findings 和文件路径，execution_allowed=false / not_run |
| rejected | 5 | Git 对象/链接等安全边界拒绝 |

原生动态 import、运行时依赖、条件插件和项目语义不能被静态文件扫描穷尽。可选 extras 不自动安装；需要额外目标级审核。`src` 布局本身只提示映射待审核，不证明一定需要安装；若项目明确依赖 `pythonpath=src` 或比正式 runner 更高的 pytest，先保守阻断。独立 Guard 是否能脱离仓库测试配置运行，必须由经过审核的契约、调用/导入映射和最小依赖证明，不能因 `--noconftest` / 空配置就自动忽略声明要求。

本批 validators 的 Git/规模通过，但当前 head 声明 pytest≥9，正式 runner 为 8.4.2，并使用 src 导入根。更关键的是当前未形成可准入的 validators 契约/Guard/Scope 来源链。因此本次预检停在执行前。详细 [W3-D 记录](progress/w3d.md) 和 [manifest 设计](../integrations/pilot/design.md) 明确区分“拒绝结果重复”与“执行试点成功”。
