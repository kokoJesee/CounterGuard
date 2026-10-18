# 字面量异常消息支持后的候选复筛

实现：`a9d19c218f61e2896b5d9f494fd318a13152eff6`。只增加[受限消息 oracle](../../literal-message-oracles.md)，未加入 legacy profile、重导出解析、类测试或依赖安装。机器记录见 [rescreen.json](rescreen.json)，逐候选记录见 [rechecks](../../../benchmarks/v2/rechecks/literal-match-v1.jsonl)，验收见 [validation.json](validation.json)，历史字节与隐私检查见 [audit.json](audit.json)。原 13 行候选及三批历史结果保持原字节。

**1 个候选解除契约提取阻塞；完整接纳场景仍为 0/13。** 原先 13 个候选并非都卡在 match。本轮重跑全部固定来源的 preflight，并对有有效选择器的测试重做投影/静态角色评估；没有穷举全部历史或所有测试。外部目标执行、H、Evidence、研究 Guard、split、学习结果均未产生。

| 候选 | 本轮投影 | 仍未完成的准入 |
|---|---|---|
| base58 | 无 Python assert，0 case | Hamcrest、其他消息写法与旧元数据 |
| base58check | 类方法不是有效顶层选择器 | unittest、旧元数据 |
| luhn | checksum 1/1 条，1 case | 历史 B/F 元数据 unknown、H、比较域 |
| stdnum | 完整树读取超单 blob 限额 | 未绕预算只取 luhn.py，未做有效投影 |
| baluhn | 无已提交测试模块可供本轮选择，case 数 null | 旧元数据、实际回归来源与比较域 |
| textcase | HEAD 6/6 条，6 case | callable-object 入口 unknown，历史修复与 HEAD 分开 |
| caseutil | 未选顶层测试 | 动态 compile/getattr、类测试 |
| casefy | main 仍为 0/153 | 控制流/print、比较方向、重导出 |
| case-conversion | 未选顶层转换测试 | 动态 setattr、unittest/parameterized |
| luhncheck | 1/1 条参数化断言，9 case | 比较目标提案，缺已确认来源 B/F、H、完整 cohort |
| termcolor | **0/2 → 2/2 条，0 → 8 case** | 实际根入口 B/F prepare 仍 unknown：重导出身份未审 |
| base45 | 未选顶层测试 | unittest/数据循环、历史 Poetry 元数据 |
| egcd | 未选顶层测试 | 运行模块导入 doctest 不在当前允许集合，docstring 投影未实现 |

“可提取”不等于可执行。null 表示本轮没有有效选择，不能当作“该项目不存在可用测试”。source revision、preflight revision、投影入口和角色评估分别记录，不能混拼通过状态。

## termcolor 实际到了哪一步

从真实 RGB 范围修复 F=`520facb24e5310a6f48736dddfe86164057a322c`（B=`db6b299abfec18223a98827f4cd6a7e475b7dfb5`）的 `tests/test_termcolor.py::test_invalid_rgb` 提取：两条 raises 分别测试 color/on_color，4 个字面量参数组合，展开为 8 case。原模式 `Expected a tuple of 3 ints in range 0-255` 进入 exception_match，没有删除或调整预期。

实际 draft 退出 0，生成 contract-proposal.v2；prepare 退出 4，生成 contract.v4、覆盖 2/2 条。**退出 4 不是执行准入通过**：测试导入根包 `termcolor:colored`，绑定器要求目标模块中有显式顶层函数，B/F 均为 target_binding_requires_review。直接模块 `termcolor.termcolor:colored` 的评估无 finding，不能与根包投影拼成通过。没有制造 H 或执行该仓库。

```powershell
counterguard contract draft --repo <termcolor-clone> --revision 520facb24e5310a6f48736dddfe86164057a322c --test-ref tests/test_termcolor.py --test-function test_invalid_rgb --target termcolor:colored --output <fresh-proposal-directory>
counterguard contract prepare --repo <termcolor-clone> --buggy db6b299abfec18223a98827f4cd6a7e475b7dfb5 --fixed 520facb24e5310a6f48736dddfe86164057a322c --contract-id termcolor.colored.rgb-range.v1 --target termcolor:colored --import-root src --test-ref tests/test_termcolor.py --test-function test_invalid_rgb --output <fresh-preparation-directory>
```

每个候选的预检命令见 rechecks 的 command；使用完整 clone 和新输出目录。其他项目没有伪选 selector、改写上游测试、移植新元数据或本地运行来消除阻塞。

## 验证与失败留痕

- 快速层：`uv run pytest -m "not slow" -q`，**838 passed、213 deselected、388.21 秒**；未跑全量。
- 新增 slow/docker 专项：**1 passed、215.34 秒**。工具自有 fixture 中 B/F 异常类型相同、消息不同：B 失败、F 通过，最小 Guard 保留唯一失败的消息 case，新 Registry 核验/幂等登记通过。最终专项实际执行 4 次目标（捕获 2、自检 2），不计作外部研究场景。
- 首轮 Docker：1 failed。操作者在执行期间修改工具源码，最终按 capture_inputs_changed_after_execution 拒绝发布；已完成 B/F 原始记录保留。源码固定后换新目录重跑，没有覆盖首轮。首轮另执行 2 次工具 fixture。
- 早期单元专项有 1 项 mock 未接到 draft 模块，修复测试接线后通过；未改标签或期望来隐藏失败。
- Ruff 通过；3 份历史 contract.v3 的序列化和生成测试与旧实现逐字节一致。旧 Schema 不改写，新格式单独导出。运行时依赖、Docker policy/runner、发布标签保持不变。

快层与 Docker 专项并行运行，耗时不是性能对比。原始 JUnit 带宿主信息和路径，只留本地；公开保存计数、有限原因、摘要和实现来源。既有四项 Docker 攻击 fixture 本轮未重跑，不能将本专项扩大为整套攻击面重验。

## 研究范围

没有取得 30–50 个真实场景，**实际已接纳数为 0**。消息提取及执行链的工程验收通过；候选 gate 仍未通过，不能声称跨项目实验完成。所有已读材料仍是已知开发候选，不是未见 holdout。

若继续推进 termcolor，下一项独立工作是根包到直接定义模块的受限重导出身份核验；之后仍需 owner H、Docker 双向捕获和自然可比目标。本轮没有实施该绑定扩展；旧式元数据 profile 继续不做。
