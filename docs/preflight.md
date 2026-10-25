# 候选仓库的只读执行预检

## 免安装/免插件候选检查

```powershell
counterguard preflight --repo <repo> --revision <full-commit-sha> --profile minimal-python --import-root src
# 根布局显式使用 --import-root .
```

当前输出 `repository-admission.v2` / `minimal-python.v1`，默认的 legacy 预检仍然保留。它读取完整的已提交树，复用 Git 对象完整性、文件/总量/时间预算，不 checkout、不 import、不运行测试、不安装依赖。

工作树里删掉 conftest 或改依赖声明，藏不住提交中的事实。

| 可机器检查的条件 | 不满足时对应前置 |
|---|---|
| 顶层 pyproject 显式 `project.dependencies=[]`，没有 dynamic dependencies；嵌套项目、legacy setup 元数据不得有未审核语义 | ③依赖安装或补足明确元数据；嵌套项目需另行审核 |
| 包根显式为 `.` 或 `src`；普通带 `__init__.py` 包/顶层模块，可解析且没有已知自定义 import 路径、namespace 或标准库/pytest 遮蔽；声明的 Python 约束不排除已审核 3.13.16（不支持的版本表达式 unknown） | ①导入布局/闭包 |
| 所有 Python imports 静态指向已列出的本地模块、检查器固定的 Linux Python 3.13 标准库词汇，或测试中的 pytest | ③第三方依赖；无法解析时 unknown，先审核①再判断是否需③ |
| 完整仓库无 conftest、pytest_plugins、required_plugins、显式 `-p`、未支持的 pytest 配置；声明的 pytest 版本/导入路径符合该候选 profile | ②受控 pytest 引导，或明确配置/runner 兼容性审核 |
| 测试只用独立断言/标准库，允许 pytest raises/approx 和 literal parametrize；无 fixture 参数、间接参数化、自定义 marker/decorator/hook、异步测试、未审核的 pytest API/别名 | ②；本检查比“pytest 内置功能都能用”更窄 |
| 无 native 扩展；没有已知动态执行/import、importlib/runpy 加载框架或未解析的 Python | ①/③独立审核；动态行为并不能由静态检查穷尽 |

可选 extras 会显示但不安装；扫描完整提交树的 imports，即使只出现在开发脚本也会列为待审。
检查器是保守的候选分类器，不是完备的 Python 依赖/fixture 证明器；固定词汇之外的标准库模块也可能 unknown。
它不读取或执行 build backend，build-system 的存在不意味着目标需要安装。

返回 0 / eligible_candidate，只表示上面这些可见条件里没发现阻塞，工程上可以优先只做①+④。这不是「只做两项就一定能跑」的语义证明：输出仍然是 `execution_allowed=false`、`verify_supported=false`。

④还包括真实契约、B/F、Docker 捕获、Guard、初始精确快照 Scope 和人工审核，尚未通用实现。在受限 Docker 里真正执行生成的契约、验证依赖闭包，仍是后续的硬门槛。

`engineering_prerequisites` 只给工具维护者描述内部开发工作，用户不需要实现这些模块。
v2 的 `user_guidance` 和同文 `next_step` 明确当前支持、用户动作、维护者责任、空的 ETA 和[跟踪落点](roadmap.md)：
静态候选可以先用 [contract draft](contract-drafts.md)准备待审核材料，但通用 verify 仍不可由用户打开；
当前只能改用确实满足来源/Scope 的已有 profile，或等待工具支持。信息不足时先修复仓库读取条件；
没有专属功能订阅/承诺日期，不让用户拿工程估算自行倒计时。v1 旧报告保留，不补写该指引。

返回 4/blocked 或 unknown 时，每项 finding 包含路径、原因、`prerequisite` 和 `next_step`：
缺失元数据/映射可以提供材料后在新提交重查；确需第三方依赖或 fixture 的项目当前不支持，需要③/②。
可以提交独立且经过审核的目标/契约闭包重新评估是否确实不需要这些能力，但不能仅隐藏原配置、
删除依赖声明、添加忽略项或用本地执行绕过。链接/对象等安全拒绝仍返回 5。

## 基础 runner 的 legacy 检查

若完整树返回 conftest/配置/fixture 待审，可以另运行 [bootstrap plan](bootstrap-plans.md)，
分别查看所选目标的候选导入闭包、选中测试投影和全仓测试环境。
全仓 finding 是保守排查记录，不必然表示选中函数真实依赖 fixture：例如 `TestCase` 方法的 `self`、
仅含 packaging 节的 setup.cfg、无 pytest 节的 tox.ini 都需按内容复核。
新计划不会把原预检改成通过，也不授予避开这些文件的执行许可。

```powershell
uv run counterguard preflight --repo artifacts/pilot/validators-discovery-v1/repo --revision 6ffd8625ee4272dade063653bff615014bdc4734
```

预检只读取完整 Git 提交树，不 checkout、不安装、不加载 conftest、不 import 目标或执行 Python。复用只读仓库检查的对象、路径和 fsck 安全 profile；最多 2048 个文件、单文件 1 MiB、总原始文件 8 MiB。结果列出每个文件的 Git/内容 pin 与实际实现摘要，重复同输入逐字节一致，不伪造执行时间。工作树删改不隐藏提交里的要求。

检查包括：嵌套 conftest、AST 中的 pytest_plugins、pyproject 的 runtime/dynamic/optional dependencies、setup/legacy pytest 配置、`required_plugins` / `-p`、最小 pytest 版本、导入根、源文件能否静态解析。支持 `tool.pytest.ini_options` 和 pytest 9 的 `tool.pytest`，以及 `pytest.toml` / `.pytest.toml`；不能只搜索四个传统文件名。格式依据 [pytest 官方配置文档](https://docs.pytest.org/en/9.0.x/reference/customize.html)。

| 结果 | 退出码 | 含义 |
|---|---:|---|
| eligible_candidate | 0 | 静态未发现当前 profile 的已知阻塞；仍不是执行许可或依赖完整性证明 |
| blocked / unknown | 4 | 已知不兼容 / 信息不够；列 findings 和文件路径，execution_allowed=false / not_run |
| rejected | 5 | Git 对象/链接等安全边界拒绝 |

原生动态 import、运行时依赖、条件插件和项目语义不能被静态文件扫描穷尽。可选 extras 不自动安装；需要额外目标级审核。`src` 布局本身只提示映射待审核，不证明一定需要安装；若项目明确依赖 `pythonpath=src` 或比正式 runner 更高的 pytest，先保守阻断。独立 Guard 是否能脱离仓库测试配置运行，必须由经过审核的契约、调用/导入映射和最小依赖证明，不能因 `--noconftest` / 空配置就自动忽略声明要求。

通用 `preflight` 保留基础 runner profile；它不会因某个仓库有专用配置而自动切换版本。validators 的固定试点另用 manifest-v5 明确锁定 pytest 9.0.3、`src` 导入根、head 内的工具方契约和 MAC oracle，并逐次授权 Docker 执行。该试点已通过，但只覆盖固定 B/F/H 提交和 10 个 MAC case；它不表示普通 `preflight` 对任意仓库都会 ready，也不证明项目的其他功能兼容。见[试点设计](../integrations/pilot/design-fork-v1.md)、[最终验收记录](results/w3d-fork-v1/final-acceptance.json)和[剩余限制](known-limitations.md#仓库接入试点)。
