# boltons 阻塞与计时归因复核

本次复核补充[原试走](../onboarding-boltons-v1/README.md)，原目录 JSON 不改写。
核查的是同一修复 `1e61524a798ea73632029a013a7686036d5c126f`；未执行 boltons 代码。
逐条来源及固定提交的对照研究见[测试启动边界](../../research/pytest-project-bootstrap.md)。

## 阻塞需要按范围解释

| 旧文件级 finding | 内容复核 | 不能推出的结论 |
|---|---|---|
| repository_conftest / test_hook_requires_bootstrap_review | tests/conftest.py 有 pytest_ignore_collect，按 Python 版本筛掉测试文件 | 所选 singularize 回归函数需要 fixture |
| legacy_install_metadata_requires_review | setup.cfg 只有 metadata/license_files | 确需安装第三方依赖，或有 pytest 配置 |
| legacy_test_configuration_requires_review | tox.ini 有 tox/testenv 节与测试命令，没有 pytest 节 | pytest 自动读取其中的测试选项 |
| test_fixture_or_nonliteral_parametrization（test_strutils.py） | 文件中有 TestCase 方法的 self 等保守待审形态；所选函数无参数 | 所选函数请求了 fixture |
| runtime_dependencies_not_declared | 该提交省略 dependencies，dynamic 只有 version；旧 profile 要求显式空数组 | 查出了非空运行时依赖 |

pyproject 的确另有 pytest doctest 选项；全仓其他文件还有真实或待审的导入路径、装饰器、动态代码等。
旧 strict 预检的 blocked 是正确执行其保守政策，**不等于所有 finding 都是所选目标的真实依赖**。
此前“确认 conftest、配置等真实阻塞”的说法应限制为“完整测试树不符合当时 strict profile”。

运行上游原生测试时，②受控 pytest 引导是明确的兼容前置；零运行时依赖不能豁免。
独立 Guard 路线仍须审核完整模块闭包、初始化、资源和 oracle，之后才可能不加载上游测试设施。
小规模便捷样本没有代表性，无法回答“无 conftest 在开源总体中是否少数”，此项**不确定**。

## 416.89 秒可以拆到哪里

| 部分 | 原始实测秒数 | 归因限制 |
|---|---:|---|
| 第 1 步墙钟合计 | 416.8927378 | 开始/结束的 monotonic_ns 均保留 |
| HTTP/1.1 失败重试 | 21.3874421 | 已测子进程时间；不是完整网络排障时间 |
| 路由变量重试超时 | 60.0855767 | 已测子进程时间；当时未继承实际 Git 配置代理 |
| 已知失败重试合计 | **81.4730188** | 确定可归于获取失败的部分，下界而非全部排障 |
| 成功获取完整对象 | 9.9661001 | 正常获取动作，与失败排障分列；不属于已证明可删的环境开销 |
| 其余区间 | **325.4536189** | 首次中断克隆、交叉诊断、工具交接、提交/许可审核等混在一起，不能拆清 |

**网络排障总耗时：不确定；排除环境后的首次材料准备耗时：不确定。**
第一次克隆被人工中断，没有独立起止记录；不能把超时设置 120 秒当成实测时长，也不把文件 mtime 伪装为精确遥测。
单纯扣掉已知失败重试还剩 335.419719 秒，但其中仍有未归因排障，不能称为“真实准备耗时”。
同样，不能把剩余区间全部归给环境，得出几十秒的准备成本。
原 7 分 48 秒是首次遇阻墙钟，完整接入时间仍为 null。

以后试走需从开始记录互不重叠的 span：`acquisition`（正常获取）、`environment_recovery`（失败重试与修复）、
`material_review`（修复/许可/期望审核）、`tool_execution`、`handoff`，并保留开始/结束 monotonic_ns、
真实 UTC 锚点、步骤、状态和简短原因。不保存代理值/凭据；未覆盖间隙单列 unclassified，不填入任一成本。
并发工作不能重复累加成墙钟，主动人工时间与代理工具时间分开。既有总耗时不回填成新分段。

## 新增的产品准备环节

[bootstrap plan](../../bootstrap-plans.md)已在真实 boltons 完整提交树上重复实测：

```powershell
counterguard bootstrap plan --repo <boltons-clone> --revision 1e61524a798ea73632029a013a7686036d5c126f --target boltons.strutils:singularize --import-root . --test-ref tests/test_strutils.py --test-function test_singularize_double_s --output <fresh-plan-directory>
```

两次计划逐字节一致；候选模块集是 boltons/__init__.py 与 boltons/strutils.py。
整个 strutils 模块中的动态 lookup 仍提示人工审核，结果 **unknown/4**；没有按函数猜测剪掉模块内其他 imports/调用。
所选测试 13 条断言，12 条直接断言表达为草案，1 条嵌套调用明确 unsupported。
引导观察分别给出 metadata、tox/testenv 与真正 pytest 节，收集 hook 单列。
它不授予执行权，不把旧 strict blocked 改成通过；B/F 捕获、H 内通用契约、Guard/Scope/Shadow 尚未完成。
当前两次命令时间仅是熟悉材料后、已有本地对象条件下的工具运行，不能用来替代首次用户审核时间或估计因果加速。

实际命令时间、源码绑定、计时原记录摘要及验证结果见同目录 `audit.json` / `validation.json`。
旧源码绑定产物不重签；本轮只新增命名空间，没有修改 Docker policy、runner catalog、冻结 scope_v1 或历史执行记录。
