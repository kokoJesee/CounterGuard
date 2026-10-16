# Python 项目的测试启动边界：boltons 与对照样本

本次核查只读取固定提交的 Git 对象、GitHub 目录树和源文件，没有导入这些项目，也没有执行其测试或安装依赖。结论用于调整接入顺序，不能作为执行授权。

## 结论及其限制

“零运行时依赖”不能推出“无需 conftest、插件或测试配置”。应把受控 pytest 启动列为**通用原生测试兼容性的必需工作包**；单个独立 Guard 能否先接入，则取决于它是否经过单独审核，确实不需要项目的启动逻辑。这是产品范围的判断，不是对开源项目比例的估计。

目前**不确定**“无 conftest”在 Python 开源项目总体中是常态还是少数。下面的五个项目是便捷样本：选取已经接触过的两个项目，再加入不同测试组织方式的三个纯 Python 工具库；没有总体名单、随机抽样或流行度加权。样本中有 conftest 和无 conftest 的情况均存在，不能把样本计数换算成产品覆盖率。

pytest 把 conftest 当作本地插件；已安装插件的 entry-point 自动发现、显式插件加载和 conftest 发现是不同路径。关闭 entry-point 自动发现并不等于禁用所有其他路径。独立 Guard 必须同时控制配置、测试路径、插件参数、环境和 conftest 加载。[pytest 插件启动顺序](https://docs.pytest.org/en/stable/how-to/writing_plugins.html#plugin-discovery-order-at-tool-startup)

## boltons 到底卡在哪里

核查提交为 [`1e61524a798ea73632029a013a7686036d5c126f`](https://github.com/mahmoud/boltons/commit/1e61524a798ea73632029a013a7686036d5c126f)。须区分“严格准入器发现需审核项”和“选中的回归断言实际依赖这些项”。

| 文件或发现 | 源码中的实际内容 | 对选中契约的含义 |
| --- | --- | --- |
| [`tests/conftest.py`](https://github.com/mahmoud/boltons/blob/1e61524a798ea73632029a013a7686036d5c126f/tests/conftest.py) | 仅 `pytest_ignore_collect` hook，按文件名中的 Python 版本标记跳过不匹配文件；没有定义 fixture | 原测试树具有可执行收集逻辑，严格整仓检查拒绝是符合既有边界的。不能将它描述为选中函数缺 fixture |
| [`tests/test_strutils.py`](https://github.com/mahmoud/boltons/blob/1e61524a798ea73632029a013a7686036d5c126f/tests/test_strutils.py) | `test_singularize_double_s` 无参数；含本地目标别名、12 个直接字面量断言和 1 个嵌套调用断言 | 选中函数不请求 pytest fixture。嵌套调用属于当前草案转换语法之外，不能静默丢失；同文件其他测试不自动成为契约依赖 |
| [`setup.cfg`](https://github.com/mahmoud/boltons/blob/1e61524a798ea73632029a013a7686036d5c126f/setup.cfg) | 仅 `[metadata]` 的 `license_files` | 没有 `[tool:pytest]`，也没有安装依赖声明；文件存在本身不能证明 pytest 配置或依赖安装确有需求 |
| [`tox.ini`](https://github.com/mahmoud/boltons/blob/1e61524a798ea73632029a013a7686036d5c126f/tox.ini) | tox 环境矩阵、`tox-uv`、dev 依赖组和 pytest/doctest 启动命令 | 没有 `[pytest]` 节；这是开发环境及命令声明，不能称为 pytest 自动加载的配置节 |
| [`pyproject.toml`](https://github.com/mahmoud/boltons/blob/1e61524a798ea73632029a013a7686036d5c126f/pyproject.toml) | `dynamic` 仅含 version；没有项目 dependencies；dev 组声明 pytest；真实 pytest 设置为 doctest flags；构建依赖为 flit_core | 基础运行时元数据与开发/构建依赖必须分开。旧严格 profile 要求显式 `dependencies=[]`，因此给出 unknown；这不能被解释为发现了真实第三方运行时依赖 |

pytest 只把带 `[pytest]` 节的 tox.ini、带 `[tool:pytest]` 节的 setup.cfg 当作相应格式的 pytest 配置；其文件名不能代替内容审核。rootdir 也不负责设置导入路径。[pytest 配置格式及 rootdir](https://docs.pytest.org/en/stable/reference/customize.html)

上述结论来自静态源码。它支持“值得审核独立 Guard 路线”，**不表示**已验证导入闭包、已完成 buggy/fixed 双向运行或已经支持 boltons 的 verify。已发布的原始试走记录仍保留其当时的严格准入结果。

## 可复核便捷样本

核查日期为 2026-10-17。boltons、validators 使用既有试走/试点提交；其余三个使用核查时读取到的默认分支提交，随后固定 SHA。GitHub recursive tree 的返回均为 `truncated=false`；“无”表示该提交完整树中没有任何 basename 为 conftest.py 的文件，不表示没有插件、配置或环境需求。

这里的“基础运行时无依赖”限定为 `[project]` 元数据：显式空 dependencies，或未声明 dependencies 且未将其列为 dynamic；不包括 extras、测试组与构建工具。PyPA 规范把运行时依赖、动态元数据和构建依赖分别定义，缺少显式空数组不等于查出了非空依赖。[pyproject.toml 规范](https://packaging.python.org/en/latest/specifications/pyproject-toml/)

| 项目与固定提交 | conftest | 可复核的测试环境差异 |
| --- | --- | --- |
| [boltons `1e61524a798ea73632029a013a7686036d5c126f`](https://api.github.com/repos/mahmoud/boltons/git/trees/1e61524a798ea73632029a013a7686036d5c126f?recursive=1) | `tests/conftest.py` | 上文所列的收集 hook；dev 组需要 pytest；选中的 singularize 函数无 fixture 参数 |
| [validators `6ffd8625ee4272dade063653bff615014bdc4734`](https://api.github.com/repos/python-validators/validators/git/trees/6ffd8625ee4272dade063653bff615014bdc4734?recursive=1) | 无 | [pyproject](https://github.com/python-validators/validators/blob/6ffd8625ee4272dade063653bff615014bdc4734/pyproject.toml) 仍声明 pytest 9、src 导入路径与 doctest；部分功能有 crypto extra，基础 dependencies 为空 |
| [more-itertools `4aeb4338ae1407d8da9723e86da99efeb446f719`](https://api.github.com/repos/more-itertools/more-itertools/git/trees/4aeb4338ae1407d8da9723e86da99efeb446f719?recursive=1) | 无 | [tox.ini](https://github.com/more-itertools/more-itertools/blob/4aeb4338ae1407d8da9723e86da99efeb446f719/tox.ini) 调用 unittest；[测试](https://github.com/more-itertools/more-itertools/blob/4aeb4338ae1407d8da9723e86da99efeb446f719/tests/test_more.py) 使用 unittest.TestCase；[项目元数据](https://github.com/more-itertools/more-itertools/blob/4aeb4338ae1407d8da9723e86da99efeb446f719/pyproject.toml) 未声明基础运行时依赖 |
| [blinker `c3364059663df1ddce32799d6b1922af89a345f6`](https://api.github.com/repos/pallets-eco/blinker/git/trees/c3364059663df1ddce32799d6b1922af89a345f6?recursive=1) | 无 | [pyproject](https://github.com/pallets-eco/blinker/blob/c3364059663df1ddce32799d6b1922af89a345f6/pyproject.toml) 的 tests 组声明 pytest-asyncio，并设置 asyncio_mode 等配置；基础运行时元数据无依赖 |
| [packaging `ef837aad3127167671eb37b9f6bd8a94ec7ce26e`](https://api.github.com/repos/pypa/packaging/git/trees/ef837aad3127167671eb37b9f6bd8a94ec7ce26e?recursive=1) | `tests/conftest.py` | [conftest](https://github.com/pypa/packaging/blob/ef837aad3127167671eb37b9f6bd8a94ec7ce26e/tests/conftest.py) 清理 markers 环境缓存并调整收集阶段 GC；[pyproject](https://github.com/pypa/packaging/blob/ef837aad3127167671eb37b9f6bd8a94ec7ce26e/pyproject.toml) 的基础 dependencies 为空，但 test 组含 hypothesis、pretend 等 |

blinker 表明“无 conftest”仍可能需要测试插件；packaging 表明 conftest 可以维护测试间状态。more-itertools 使用 unittest，框架选择本身就是混杂因素。因此，这份表只反驳“零运行时依赖足以判断启动兼容”的假设，不回答总体占比，也不声称五个项目均已完成 CounterGuard 执行准入。

## 产品顺序建议

1. 通用接入必须明确选择执行路线：独立生成 Guard，或原生测试。前者审核目标导入闭包和明确的输入/输出契约；后者还必须审核项目配置、conftest/hooks、fixtures 和插件。不要用仓库有无某个文件替代这一区分。
2. 先完成有限、零依赖的独立 Guard Docker bootstrap。整个仓库中发现的 hook 或配置保留在报告中；只有经过新的独立路径审核，才能说明它们为什么不参与该次运行。旧 strict profile 不应被悄悄放宽。
3. 受控 pytest bootstrap 应作为通用原生测试路线的独立里程碑，而不是低优先级兼容附加项。其边界包括固定版本、配置白名单、受控插件依赖、收集与 hook 执行、完整来源绑定以及 Docker 攻击 fixture。没有这些实现之前，依赖它们的项目仍为不支持。

以上是设计推论。不能从本次静态样本更新现有工作量估算为实测工时，也不能把未知成本写成固定交付日期。若要回答总体频率，需要先定义项目总体和抽样方法；若要优化接入成功率，应优先记录实际候选项目在两条路线上的阻塞原因。

## 复核方法

对上表任意项目，可用 GitHub 的固定提交 recursive tree GET 重查 conftest 文件；必须先确认响应未截断。下面只读取远端 JSON，不会加载目标 Python 代码：

```powershell
$ownerRepo = 'pypa/packaging'
$revision = 'ef837aad3127167671eb37b9f6bd8a94ec7ce26e'
$tree = Invoke-RestMethod "https://api.github.com/repos/$ownerRepo/git/trees/${revision}?recursive=1"
if ($tree.truncated) { throw 'Incomplete tree: no absence conclusion is allowed' }
$tree.tree | Where-Object { $_.path -match '(^|/)conftest\.py$' } | Select-Object path
```

有完整本地 Git 对象时，等价的目录审核为 `git ls-tree -r --name-only <固定提交>`；用 `git show <固定提交>:<路径>` 查看上表配置和测试。网络/API 不可用、树被截断或文件无法读取都应保留为未完成，不把空输出当作“没有 conftest”。不需要 checkout、pip install 或执行 pytest。
