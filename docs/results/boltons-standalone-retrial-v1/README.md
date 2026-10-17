# boltons 在 standalone 交付后的复跑

本记录接续[首次试走](../onboarding-boltons-v1/README.md)和[阻塞复核](../onboarding-audit-v1/README.md)，
使用同一真实修复及当前实现重新运行。机器事实见 [trial.json](trial.json)，旧 JSON、Git 对象与源码未改写。

**结论：最远生成 contract.v3；尚未捕获 Evidence，也没有进入 Shadow。**
非固定项目的受限闭环已实现，但这个具体目标的运行闭包仍 unknown，且没有 owner H。
boltons 执行次数为 0，Docker 中也为 0；没有用本地执行替代 Docker，没有删除 conftest 或修改上游测试。

## 来源与实际步骤

- 仓库：[mahmoud/boltons](https://github.com/mahmoud/boltons)，BSD-3-Clause，固定树 111 个文件。
- B：`55dfe5077bcb5fa76611b5f2a557ea6c442ad87c`。
- F：[1e61524a798ea73632029a013a7686036d5c126f](https://github.com/mahmoud/boltons/commit/1e61524a798ea73632029a013a7686036d5c126f)，唯一父提交为 B。
- 目标 `boltons.strutils:singularize`，源测试 `tests/test_strutils.py::test_singularize_double_s`。
- 工具提交 `72316b7`，包源码摘要与已发布 0.5.0 wheel 一致；本次公开修改仅涉及文档，没有改变分类政策。

| 实际命令 | 退出码 | 工具墙钟秒 | 结果 |
|---|---:|---:|---|
| bootstrap plan，第一次 | 4 | 3.627 | 闭包 unknown；完整树和上游引导观察保留 |
| contract prepare，第一次 | 4 | 4.400 | 生成 contract.v3；B/F 运行评估均 unknown |
| bootstrap plan，第二次、新目录 | 4 | 2.971 | 与第一次计划逐字节一致 |
| contract prepare，第二次、新目录 | 4 | 4.180 | 契约和准备报告均逐字节一致 |
| bootstrap bind，以 F 代 H 的显式负例 | 5 | 3.048 | contract_missing_from_head；不把外置契约注入提交 |

最后一项是有意验证拒绝路径，不是一次符合前置的 H 绑定。正向绑定、capture、compile、Registry/Shadow 均未尝试。
plan 和 prepare 返回 4 的含义不同：所有计划都不能执行；prepare 本来就要求人审，必须另读两侧运行评估，不能只看退出码。

以下命令只读使用完整 clone，不 checkout/导入目标；每次重复都换新输出目录：

```powershell
counterguard bootstrap plan --repo <boltons-clone> --revision 1e61524a798ea73632029a013a7686036d5c126f --target boltons.strutils:singularize --import-root . --test-ref tests/test_strutils.py --test-function test_singularize_double_s --output <new-plan-directory>
counterguard contract prepare --repo <boltons-clone> --buggy 55dfe5077bcb5fa76611b5f2a557ea6c442ad87c --fixed 1e61524a798ea73632029a013a7686036d5c126f --contract-id boltons.singularize.double-s.v1 --target boltons.strutils:singularize --import-root . --test-ref tests/test_strutils.py --test-function test_singularize_double_s --output <new-preparation-directory>
# 显式负例：F 不含契约，预期退出 5，不是有效 H。
counterguard bootstrap bind --repo <boltons-clone> --head 1e61524a798ea73632029a013a7686036d5c126f --contract-ref contracts/boltons-singularize.v1.json --output <new-negative-check-directory>
```

## 具体卡在哪里

1. **调用分类过粗。** 候选运行文件仅为 boltons/__init__.py 与 boltons/strutils.py。
   B/F 均只有一个去重 finding：dynamic_code_or_lookup_requires_review。
   对 F 的 AST 进一步核对，触发规则的 7 处语法调用都是 re.compile，位于 65、66、321、361、665、767、1217 行。
   分析器按调用名最后一段 compile 匹配，也就把正则编译保守归入此类。
   这不能当作发现了 builtins.compile、eval 或动态 import；AST 中写着 re.compile 也不是运行时绑定未被改变的证明。
   未因 singularize 未直接出现这些调用就剪掉整个模块，也没有按项目名称添加放行项。
2. **缺少由所有者提交契约的 H。** 外置准备文件已经生成，但不等于契约存在于 Git head。
   当前 profile 要求 H 直接接在 F 后，只新增那一份契约，保留上游源码/测试字节。
   本轮没有代造 H，也没有创建 fork、提交或推送 boltons。即使补齐 H，第一项 unknown 仍会阻止捕获。
3. **投影不是原测试的全量迁移。** 13 条断言中表达了 12 条直接字面量断言；301 行的嵌套幂等性调用明确 unsupported。
   这条保留项不是本次自动拒绝的原因，但仍须审核契约只覆盖已表达行为，不能把分母说成 13 条均已迁移。

上游 conftest 的 pytest_ignore_collect、配置节和未显式写 dependencies 的声明仍保留在观察中。
source-only profile 已接受静态省略且不 dynamic 的依赖声明；本轮阻塞不再概括为“仓库有 conftest”。
完整上游原生测试路线仍需受控 pytest 引导，不能据此改动旧 strict preflight 的标准。

## 到 Shadow 还缺什么

先为调用识别设计有版本的、别名/重绑定感知的规则和攻击测试；只有确实符合受限规则的调用才能进入 review_required，
真动态调用仍 unknown。当前版本没有“填一段审核理由就覆盖 finding”的接口。
规则至少需处理 import re 的别名、同名导入/赋值/参数、属性重绑与嵌套作用域；不能只比对 ast.unparse 的字符串。
仅将 compile 从检查列表删除、允许一切 obj.compile，或只保留 singularize 的函数体，都不合适。
本轮保留旧政策和旧包源码，因此没有新授权，也不需要重物化既有来源链。

规则满足后，用户在自己控制的 fork 中审核并提交仅含契约的 H，再依次 bind、Docker 双向 capture、独立核验、
最小失败集 compile/B/F 自检、登记 Candidate、审核精确快照 Scope，最后显式提升 Shadow。
届时必须重新生成新 ID 的证据，不能给本次 not_run 补签成成功。

## 计时、失败与公开发布

当前脚本的五条命令合计 18.227 秒；脚本覆盖 23.678 秒，另含 Git/AST/只读指纹检查和 2.802 秒发布 API 读回。
已有完整本地对象、操作者熟悉目标，未进行新获取，也未计入脚本外的人工审核和交接。
它是遇阻复验耗时，完成接入时间仍为 null，不是新的“30 分钟内完成”证据。

开始时误选了先前获取失败的残留目录：首条命令 1.569 秒返回 unsupported_reference，
辅助脚本随后因错误输出非 JSON 停止。原始 stdout/stderr、计时及失败目录保留；改用旧记录明确的完整 clone 后使用全新输出目录。
该失败属于本地材料选择错误，不计为 boltons 兼容性结论，也没有改坏旧 clone 来强行通过。

同时从公开 GitHub API 重新核对 [v0.5.0 Release](https://github.com/kokoJesee/CounterGuard/releases/tag/v0.5.0)：
非草稿、prerelease、有发行说明、6 个附件的大小与 SHA-256 均匹配[原发布收据](../beta-v0.5.0/delivery.json)。
这不是只有 tag；本项目未向 PyPI 发布。本记录没有修改 Release、标签或已发布附件。

公开材料只选择来源、枚举状态、计数与摘要，不上传原始 CLI 日志、Git bundle 或机器路径。
摘要属于维护者观察，不是签名、所有者身份认证或执行授权。

本轮只更新说明与新增复验收据，没有改运行代码、重新构建或覆盖 0.5.0 发行物。
文档链接、摘要、公开变更隐私与 Ruff 检查见 [validation.json](validation.json)；未重跑 pytest 全量或 Docker 攻击测试，
也没有把上一轮 998 项全绿记录改称本轮的新测试结果。
