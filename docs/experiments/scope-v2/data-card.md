# 候选来源与可行性

状态：开发期来源探测，尚无纳入 scope_v2 的场景。最新[colored 源码/映射审核材料](../../results/colored-review-v1/README.md)已准备，维护者准入裁决与研究桥接仍待完成。
候选登记见 [candidates.jsonl](../../../benchmarks/v2/candidates.jsonl)，实测见[首批](../../results/scope-study-feasibility-v1/README.md)和[第二批回执](../../results/scope-study-feasibility-v2/README.md)。这些材料已被开发者阅读，不会再当作独立保管的未见留出集。

## 采集原则

先找真实修复和已有回归依据，再核对同语义的其他项目；不按 learner 是否学得好筛样本。获取源码只读 Git 对象，不 checkout/运行上游安装脚本，不执行上游测试；原始 clone/诊断、准备链和绝对路径留在本地。这里只公开精确提交、文件摘要、有限状态/计数与再现入口。

首批按两类有公开描述的 Python 实现探测：Base58 编码及 Luhn 校验。共享算法名称只说明检索方向，不能证明接口、oracle、边界行为或来源独立性相同。B/F 的形成、许可和分组仍需逐场景审核；没有按算法名称宣布 cohort 成立。

独立修复、固定目标、Guard/样本行分别计数。三批共 13 个仓库候选 **不等于 13 个已复现修复**；最初只读探测时，已接纳场景、Evidence、新 Guard 和目标执行均为 0。
后续 termcolor 的真实来源闭环见文末；它不改变独立跨项目研究场景仍为 0 的结论。没有冻结 split/context/protocol，也没有训练或读取 scope_v2 最终标签。

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

维护者随后批准契约及 fork/H/Docker 操作，已完成 [termcolor 真实来源闭环](../../results/termcolor-source-v1/README.md)：
所有者 fork 的 H 只新增契约；两轮完整 capture 均为 B 8 failed、F 8 passed，失败集与 case 结果一致、run ID 不同；
Evidence/Guard 独立核验通过，Guard 保留 8 个实际失败 case 并完成 B/F 自检，本地登记为不可调度的 Candidate。
**已验证来源修复数为 1，完整跨项目研究场景仍为 0**；新记录独立追加，前面的“0”是对应轮次的历史结果。
自然独立比较目标未确认，研究桥接/学习/冻结未启动；下一步先核对可比性，不把 8 case 当成 8 个场景。

最新[受限重导出重查](../../results/static-reexport-v1/README.md)将 termcolor 原根入口的 B/F 角色评估均推进到
review_required、无 finding；真实 prepare 已生成独立 contract.v5，仍保留原 2 条消息断言、8 case。
该次只重查该候选，未重复声称完整筛查 13 个。当时 owner H、实际外部双向 Evidence、自然独立比较目标尚未取得，
完整接纳场景为 0；工具自有 Docker fixture 的通过不计研究样本。当时先审阅已准备契约和所有者提交路径，
不制造 H、不借直接模块入口替换根包投影。legacy profile 继续不做。

此前消息 oracle 扩展后已[复筛全部 13 个候选](../../results/literal-match-rescreen-v1/README.md)：termcolor 从 0/2 条变为 2/2 条、8 case，当时根包重导出入口仍 unknown，完整接纳场景为 0。其余候选没有因消息语法扩展消除其他阻塞。复筛独立保存，不覆盖历史行；30–50 个场景仍未取得，不以工具 fixture 或 case 数替代。

消息扩展前的第三批核对了 termcolor、base45、egcd，详情见[历史回执](../../results/scope-study-feasibility-v3/README.md)。当时 termcolor 的真实 B/F 两侧直接模块角色评估均无 finding，但 raises 的 match 断言与根包重导出尚不支持；base45 的历史 B/F 仍是旧 Poetry 元数据，egcd 的运行模块导入 doctest 被明确判 unknown。该批均未执行，没有把工程缺口变成成功样本。

这轮完成了研究规格、独立历史核对，以及首批来源/阻塞探测；**尚未完成候选可行性准入**，因此没有进入研究执行适配、数据冻结或训练。

继续采集的优先项是：有明确静态项目元数据、直接字面量回归断言、完整真实 B/F 和所有者 H 路径的现代小型项目，并另找自然可比目标。所有候选仍留在登记中，不把未通过记录删掉。

如果要优先用上述旧项目，须先另行设计并审查旧式源码元数据的受控 profile，或受限 Hamcrest/unittest/消息断言投影；它们不是给一个“审核理由”就能开启的开关，也不包含在现有能力声明内。已给出[旧式源码支持提案](legacy-source-proposal.md)，维护者已选择继续按现有 profile 筛选，该提案暂不实施。不得静默放宽生产默认 profile、删除安装元数据检查或借本地执行取得结果。

若后续仍找不到自然跨项目可比的数据，应回到[研究规格](design.md)的范围决策：明确减少主张或提出独立的同项目探索轨，而不是宣称跨项目实验已经跑通。

## 输入校验方向的继续核查

[本轮核查](../../results/input-validation-search-v1/README.md)优先重查 textcase / luhncheck，再按 pathvalidate、semver、isodate、luhn、base58 顺序进行，并补查 Click 的 RGB 校验修复。
8 次 preflight、18 次 HEAD/B/F 直接定义诊断和 4 次固定测试 AST 投影均已记录；没有目标执行、新 H、标签或数据冻结。
pathvalidate、semver、isodate、Click 有明确漏拒绝补丁线索，但新增可接纳来源/比较目标均为 0。
已有 termcolor 来源闭环仍为 1，完整跨项目场景仍为 0；不把补丁数或回归 case 数当成已复现场景。

此前 Luhn verify ↔ luhncheck 的提案有一项新限制：较早核心代码明显相似，是否借用或有共同来源不确定，独立性未通过。
luhncheck 的现成字母回归样例是异常 → False，不是原先接受非法值；空串漏拒绝仅有源码线索，没有受检固定 F 回归断言。
详见[谱系与回归核查](../../research/luhncheck-input-validation.md)。这些更正不覆盖或删除前面的历史发现。

Click 是更接近 termcolor 的 RGB 共同域候选，但参数展开投影、完整闭包和调用/oracle 审核仍有阻塞。
消息差异是否构成合法反例尚未裁决，不删除 match 来制造可比性。validators 不再用于本轮，pytimeparse 按维护者要求排除；legacy profile 继续不做。

## Click 的有界可行性评审

[定点评审](../../results/click-feasibility-v1/README.md)已完成：正式 bootstrap plan 退出 4；固定 F 的完整闭包有 16 模块、30 条保守 finding，并定位对应语法，而非宣称发现 30 个漏洞。
原测试有 2×18 个理论调用，当前投影 0/1 条；公开根包导出另报 export_root_statement_unsupported。
作为比较目标并不必须把这 36 个调用转换成新来源契约，也不要求新的 B/F/H 来源捕获链。

自然 RGB 共同域与谱系支持依据见[语义调查](../../research/click-rgb-contract-comparability.md)；完整来源消息策略仍保留，Click 消息不同是待审合法反例假设，不是已裁决标签。
当前 AST 提取对 Click F style 仅得到 branch:none，对其 RGB helper 和 termcolor F colored 均拒绝，研究桥接/特征支持还需独立设计。
本轮没有修改产品或执行外部目标；已验证来源仍为 1，已接纳比较目标/完整跨项目场景仍为 0。

Click 准入不是一项参数展开小补丁，本轮暂停其执行接入，不扩张 profile。下一轮限定最多 5 个较小独立 RGB/范围校验目标，先检查固定元数据、普通函数、根包和闭包，再查共同域；不要求目标自带新修复。
该批仍无合格目标时停止扩搜，提交研究范围/通用准入投入的选择，不自动降低标准或改轨。

## 五项 RGB 目标筛查已收束

[有界筛查](../../results/bounded-rgb-targets-v1/README.md)完成 colorist、sty、ansicolors、colored、rgbprint 五项，候选预算用尽。
三项在旧式元数据阶段停止且未跑后续检查；两项现代包均实际 preflight=4 并读取完整树，根导出和直接定义闭包仍未通过。
新增可接纳比较目标仍为 0，已有真实来源仍为 1，完整跨项目场景仍为 0；没有执行外部目标、分配标签或冻结数据。

本批保留了更具体的目标提案：colored 上游测试明确要求 RGB 夹紧，cprint 普通入口可原样表示源八个输入；
其完整闭包 12 文件，三个类/元类钩子被保守规则记为模块钩子，根包导出仍独立 unsupported。
8/8 仅是字面量映射工作表，不是语义裁决或运行通过；不能把夹紧政策解释为漏拒绝缺陷。

该批停止同方向扩搜，提交[colored 受限支持提案](colored-minimal-support-proposal.md)与缩窄实证主张的选择。
当时初估 3–6 人日，不含研究执行桥接；不做 legacy、kwargs 提取或 Click 支持。随后选择和实测见下。

## 受限支持及源码/调用审核的当前状态

维护者已批准受限支持，[工程验收](../../results/static-reexport-v2/README.md)完成 contract.v6 / binding.v4、
closure.v2 和有限类钩子识别；旧默认 grammar 保留。工具自有 Docker fixture 通过不计外部研究样本。
colored 固定提交的 50 文件、12 文件闭包和 3 个钩子均已记录，仍为 review_required / not_run。

后续[源码审读与映射审计](../../results/colored-review-v1/README.md)保留全部 8 case、ValueError 及原消息子串。
机器只核对字面量、角色、断言身份和来源控制参数，不能替维护者批准语义或标签。
其中 4 个越界三元组有上游夹紧测试依据，4 个长度错误缺少同等独立规范依据，明确列为待裁决。
完整闭包的类体生成、环境读取及条件 Windows native 初始化均纳入审读，没有删分支来放行。

谱系检查包括固定历史、根提交、当前/初始接口及相关 RGB 实现；可达提交没有交集，但这不证明无代码借用。
维护者仍须裁决分组与整行可比性；没有给目标分配标签。已验证来源修复保持 1，完整研究场景保持 0。
来源的历史 Evidence/Guard 不能冒充当前实现验收，需在代码稳定且获执行批准后用新 ID 重新物化。

研究工程的支持范围见[研究重放](../../research-replay.md)，限定严格输入与自有 fixture，
不直接执行 colored，不开放最终标签。来源/可比性材料与工程桥接验收分别记录，
不能以实现执行通道代替外部样本的准入裁决。开发实施方案只在本地维护。
新 AST/context/接口分类尚未冻结，数据也不足以独立构成 initial/refinement/holdout；不更改标准来填空。
