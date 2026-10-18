# 候选来源与可行性

状态：开发期来源探测，尚无纳入 scope_v2 的场景。候选登记见 [candidates.jsonl](../../../benchmarks/v2/candidates.jsonl)，实测见[首批](../../results/scope-study-feasibility-v1/README.md)和[第二批回执](../../results/scope-study-feasibility-v2/README.md)。这些材料已被开发者阅读，不会再当作独立保管的未见留出集。

## 采集原则

先找真实修复和已有回归依据，再核对同语义的其他项目；不按 learner 是否学得好筛样本。获取源码只读 Git 对象，不 checkout/运行上游安装脚本，不执行上游测试；原始 clone/诊断、准备链和绝对路径留在本地。这里只公开精确提交、文件摘要、有限状态/计数与再现入口。

首批按两类有公开描述的 Python 实现探测：Base58 编码及 Luhn 校验。共享算法名称只说明检索方向，不能证明接口、oracle、边界行为或来源独立性相同。B/F 的形成、许可和分组仍需逐场景审核；没有按算法名称宣布 cohort 成立。

独立修复、固定目标、Guard/样本行分别计数。当前两批共 10 个仓库候选 **不等于 10 个已复现修复**；已接纳场景 0、已捕获 Evidence 0、已编译新 Guard 0、目标执行 0。没有冻结 split/context/protocol，也没有训练或读取 scope_v2 最终标签。

## 实际发现

| 候选 | 已做的检查 | 具体边界 | 仍未完成 |
|---|---|---|---|
| keis/base58 | 固定真实修复提交；preflight 4、bootstrap plan 4 | 运行闭包 review_required、无闭包 finding；选定回归函数用 Hamcrest，不产生 Python assert，投影明确 no_assertion_syntax。修复针对 ValueError 消息，当前 raises oracle 只表达异常类型 | 消息 oracle、人审/H、来源捕获、可比接口与独立性 |
| joeblackwaslike/base58check | 固定 HEAD 与文件；preflight 4；尝试选 test_encoding 时 plan 2 | 回归入口是 unittest 类方法，不是支持的顶层测试函数；该次选择错误不能当成有效的运行闭包评估 | 真实 B/F 未选择、契约投影、H、运行准入与可比接口 |
| mmcloughlin/luhn | preflight 4；静态闭包无 finding；另按真实 Python 3 修复准备契约，退出 4且产出 contract.v3 | 1/1 条现有字面量断言成功投影；B/F 都因 legacy_install_code_requires_review + project_metadata_unavailable 为 unknown。纯 AST 闭包无 finding 不代表完整绑定已通过 | 元数据支持、所有者 H、双向捕获与来源核验 |
| arthurdejong/python-stdnum | 固定 HEAD；preflight 4；完整提交读取遇 blob_budget_exceeded | 816 个 blob 合计 4,815,864 字节，最大单 blob 为 1,219,340 字节，超过当前单文件 1 MiB 限额；不是 8 MiB 总量问题。未绕过整树检查只取 luhn.py | 受支持快照、独立契约/来源/目标闭包；不是确认其 Luhn 代码有问题 |
| benhodgson/baluhn | 只读核对固定树、源码/README/LICENSE | 有 Luhn 默认 base10 语义说明；仅凭算法相同不足以宣布与来源 Guard 可比 | CLI 准入、运行闭包、测试投影均未测；B/F/H 未选择 |

前三个库的安装元数据缺项都需逐入口解释：strict preflight 的 unknown 不自动否决 source-only，但后者的实际角色评估也不能忽略。Luhn 的 prepare 已实际确认 B/F 角色均 unknown，而不只是沿用旧 preflight 的结论。

## 优先保留的修复提案

[mmcloughlin/luhn 的真实提交](https://github.com/mmcloughlin/luhn/commit/b611e357da3a5e17abf9b8dfe40b111eb1cdc50d)把 Python 3 中不可切片的 map 改为 list(map(...))。B=`b64d5682b2f2e0655b88543169bffddfa5bd1680`，F=`b611e357da3a5e17abf9b8dfe40b111eb1cdc50d`，目标为 `luhn:checksum`。该修复没有新增测试；契约来自 F 树中已有的 `test.py::test_checksum_len1`，不能说成“F 新增的回归测试”。

已提取的单条断言等价于 `checksum('7') == 7`，证据定位和原始测试摘要保存在准备报告中。它仍是待人审提案，不是“B 失败、F 通过”的实测结论。当前不制作 H 或创建 fork：补 H 本身也不能消除元数据 unknown。

可重复的只读准备命令（使用完整 clone，输出目录必须全新）：

```powershell
counterguard contract prepare --repo <luhn-clone> --buggy b64d5682b2f2e0655b88543169bffddfa5bd1680 --fixed b611e357da3a5e17abf9b8dfe40b111eb1cdc50d --contract-id luhn.checksum.python3.v1 --target luhn:checksum --import-root . --test-ref test.py --test-function test_checksum_len1 --output <fresh-preparation-directory>
```

预期退出 4不是“已可执行”：本次报告有 contract.v3 与 1 个 case，B/F runtime assessment 均 unknown，execution_allowed=false。换工具版本时须读新报告，不沿用这里的状态。

## 第二批与更具体的比较提案

第二批依次读取 textcase、caseutil、casefy、case-conversion，再沿既有校验算法方向加入 luhncheck；逐项结果和固定提交见[第二批回执](../../results/scope-study-feasibility-v2/README.md)。其中 textcase 与 luhncheck 的严格 preflight 退出 0，但只有后者同时具有普通函数入口、无 finding 的 source-only 角色评估和支持的测试投影。

luhncheck 的 1 条参数化断言展开为 9 个 case。textcase 的 HEAD 有 6 条 snake 断言可投影；其历史真实修复另以 upper 为目标准备，投影 2/5 条断言，B/F 都因 callable-object 入口 unknown。caseutil/case-conversion 的动态查找，casefy 的测试控制流/重导出等边界均保留；没有通过修改上游测试消除它们。

另从已有 Luhn 修复提取 `test_valid` 的布尔 verify 契约，1/1 条断言；它与 luhncheck 的共同非空 ASCII 十进制域形成了更具体的比较提案，仍需规范、源码谱系、owner H 和执行准入审核。它复用同一修复，不增加独立 scenario。整数 checksum 与布尔 is_luhn 不能直接当作相同 oracle。

## 进度判定与下一步

这轮完成了研究规格、独立历史核对，以及首批来源/阻塞探测；**尚未完成候选可行性准入**，因此没有进入研究执行适配、数据冻结或训练。

继续采集的优先项是：有明确静态项目元数据、直接字面量回归断言、完整真实 B/F 和所有者 H 路径的现代小型项目，并另找自然可比目标。所有候选仍留在登记中，不把未通过记录删掉。

如果要优先用上述旧项目，须先另行设计并审查旧式源码元数据的受控 profile，或受限 Hamcrest/unittest/消息断言投影；它们不是给一个“审核理由”就能开启的开关，也不包含在现有能力声明内。已给出[旧式源码支持提案](legacy-source-proposal.md)，维护者已选择继续按现有 profile 筛选，该提案暂不实施。不得静默放宽生产默认 profile、删除安装元数据检查或借本地执行取得结果。

若后续仍找不到自然跨项目可比的数据，应回到[研究规格](design.md)的范围决策：明确减少主张或提出独立的同项目探索轨，而不是宣称跨项目实验已经跑通。
