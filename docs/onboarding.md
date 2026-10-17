# 第一次接入：用户需要做什么

适用对象是零运行时依赖、根目录或 `src/` 中的普通 Python 包、独立断言测试。
可先运行[静态准入](preflight.md#免安装免插件候选检查)观察全仓情况。该旧 profile 的结果不替代独立 Guard 闭包判断；
包含 conftest 的仓库仍可单独检查目标是否依赖它。
当前已交付[受限通用 Docker 捕获](standalone-capture.md)及[最小 Guard/快照 Scope/Shadow](standalone-guards.md)；不能仅凭静态候选分类执行。
目前真正可执行的仍是[已审核 profile](project-admission.md#最小可接入范围)。

## 首次准备的责任清单

准备 contract.v3 后，先查看 preparation.json 的 runtime_assessment 与 buggy_runtime_assessment。
任何一侧仍 unknown/blocked 时，不能只填审核理由继续 capture；先解决具体 finding，不必急着 fork 或提交 H。
只有 proposal/preparation、不含 H 的本地文件或一次成功 plan，都不能替代完整来源绑定。

| 顺序 | 用户/项目所有者确认什么 | 工具负责什么 | 当前状态 |
|---|---|---|---|
| 1 | 选择一个真实修复，给出仓库、buggy/fixed 的完整提交 SHA，并确认许可证和缺陷背景 | 读取两棵 Git 提交树，核对来源，不要求手工复制两份源码 | 支持受限普通包 B→F→H 线性来源；任意历史仍不支持 |
| 2 | 编写或审核契约：输入、预期行为、稳定 case ID；把最终契约提交到 assertion head | `contract draft` 提取待审断言；`contract prepare` 准备含 B/F 的 contract.v3，由所有者单独提交 H，`bootstrap bind` 重建来源 | 已有受限准备/来源核验命令；不自动批准或执行 |
| 3 | 确认目标符号、`.`/`src` 导入根、需要纳入的本地依赖及变更映射 | 静态检查声明、imports、Git pins；后续仍须在受限 Docker 内核对 | `preflight` 做全仓分类，`bootstrap plan` 并列闭包与测试环境；仅明确审核后的独立契约可进入新捕获 |
| 4 | 审阅首次捕获结果，确认 buggy 的失败确为缺陷、fixed 符合契约 | Docker 中分别运行 buggy/fixed，保存真实 JUnit/日志；基础设施错误不能当作缺陷 | `bootstrap capture` 与 `bootstrap verify-evidence` 已实现；独立本机审核理由必填，无本地执行回退 |
| 5 | 审核首版适用边界 | `bootstrap compile` 自检最小失败集并生成**已审核 B/F 完整闭包的精确快照**；新源码 unknown | 已支持受限 Guard v3；不默认 always-applicable、不伪造训练样本、不继承 scope_v1 的学习结论 |
| 6 | 审核来源后把 Candidate 提为 Shadow；有实际接受记录后才考虑 Active | 追加状态事件，保存操作者标签/原因；每次执行重验来源与状态 | 不自动提升，也不把本机 actor 文本当作远程身份凭据 |

这是 **6 项人工决策**，不是 6 条命令或 6 次点击；同一维护者可以兼任所有者和审核者。
有现成回归测试时，第 2 项现在可运行[静态草案命令](contract-drafts.md)。它只生成待审核 proposal，
不把 helper、fixture、复杂 oracle 或嵌套调用假装成已支持，也不能直接进入 Registry 或执行。
此前“可以转换”的表述没有说明能力范围：当时只有 validators 专用投影器，没有通用用户命令。

首次 Evidence 需要的是可定位的两份**提交来源**，而不是让用户手工维护 buggy/fixed 两套目录。
若修复提交为 F，通常 B=F 的父提交；存在合并、依赖或构建差异时需明确实际 B，不能猜测。
契约可在独立 owner 提交 H 中加入，必须真实存在于 H；不往执行时的只读快照偷偷注入外置契约。

## 日常 verify

接入完成后，用户提交改动，提供 base/head 和新的输出目录；配置、Registry 和 runner ID 可由维护者预先固定：

```powershell
counterguard verify --repo <repo> --base <base-sha> --head <head-sha> --config <config> --registry <registry> --runner-id <reviewed-id> --output <new-output>
```

日常需要 **1 次运行、1 次查看结论**；有受支持的 CI 后运行步骤可自动化。
不需要每次重写契约、复制源码或重新捕获。若源代码超出精确快照 Scope，结果为 unknown/4，
维护者必须审核新的适用证据，不能把它自动当成不适用或通过。
这意味着当前版本尚不能对任意后续源码变动持续泛化；“日常操作少”不等于“维护边界没有成本”。

Shadow 违规只记录；Active 的适用违规返回 1；执行故障/unknown/完整性失败分别返回 3/4/5。
契约、来源闭包、runner 或工具实现变化时按[重算规则](data-contracts.md)新建产物，不覆盖历史。

## 30 分钟的门槛

已有[原开发代理试走](results/onboarding-boltons-v1/README.md)及[standalone 交付后的复跑](results/boltons-standalone-retrial-v1/README.md)：同一真实 boltons 修复，逐项保留遇阻与未执行状态。
首轮约 7 分 48 秒后因读取环境阻塞停止，随后正常权限复核确认项目本身也不满足当前执行前置；
没有完成首次 Evidence/Shadow。新版最远生成 contract.v3，调用分类仍 unknown，且没有 owner H；
它们都不是外部用户研究或“几秒/几分钟完成接入”的证明。
完整接入耗时与流失情况仍**不确定**，不能承诺首次接入在 30 分钟内，也不能把工程人日当作用户操作时间。

产品验收应单独记录：首次准入命令耗时、准备六项材料的人工时间、每项阻塞及是否需要维护者帮助。
原试走第 1 步 416.89 秒没有完整分段遥测，不能扣出准确的网络排障或纯准备耗时；
[复核记录](results/onboarding-audit-v1/README.md)区分已知失败重试、成功获取与未归因区间。
后续试走从开始记录互不重叠的获取、环境恢复、材料审核、工具运行和交接区间；原始总耗时保留。
已有真实修复和测试的项目才适合检验“30 分钟内获得首个 Shadow 结果”这一**待验证目标**。
没有修复或正确行为定义时，应先解决材料问题，不让用户为了完成向导编造缺陷。
首次 Evidence 到 Guard/Scope/Shadow 的受限闭环已补齐；若该目标仍达不到，应依据实际计时优化材料准备与配置生成，继续增加参数说明并不能解决门槛。

当前 [CI 示例](github-actions.md)用的是工具自带可信 fixture，不是新项目接入向导或用户效率证明。
