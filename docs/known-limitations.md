# 当前 MVP 的范围与限制

本文件记录当前可信本地 MVP 的能力边界。打包、安装和正式验收以 [D14 记录](progress/day14.md) 为准；攻击面覆盖以 [排查清单](attack-surface-checklist.md) 为准。

## 输入和执行

- Python-only、pytest-only，仅支持显式目标及当前契约类型/断言模板。
- mvp.yaml 只接受 JSON 语法这一 YAML 子集；不支持通用 YAML 缩进、注释或锚点。完整内容见 [快速开始](quickstart.md)。
- 标准 Demo 使用录制候选、固定可信模板和本地 fixture，未接入实时模型或任意新 oracle 生成。
- pytest 是可选 runner extra；基础安装缺少它时，Demo/Pipeline 和执行器提前拒绝执行并提示安装，退出 3，不把缺依赖当作测试违规。检查元数据/模块存在不保证任意损坏安装的功能正常。
- v0.1.0 wheel/tag 的执行器仍只面向可信本地代码。源码开发版 W3-B 的正式 Python runner 已完成四项攻击复验、镜像/依赖字节锁定及归档恢复；W3-C 本地 Registry 已验收。validators 自身准入因 pytest9/src、外置契约/位置参数/装饰器/返回类和 Evidence/Scope 缺口被拒，未执行仓库代码。pytest/容器隔离也不是通用 Python 沙箱或结果远程证明。
- 合约/模块 context 是显式确认和审核的元数据，自动 AST 提取不会替代人的语义判断。
- Docker 授权 v1 只支持 replay；新未知仓库的 capture/compile 尚未接入 Docker，默认入口仍只可用于可信本地样本。未知代码的新 Guard 来源链必须先完成独立的 Docker 捕获/自检设计，不能调用本地入口绕过本次准入。

W3-A 源码版已支持 [只读仓库检查](repository-inspection.md)，v0.1.0 wheel/tag 保持原样。inspect 的 ready / affected 只表示声明的文件映射结果，不审核依赖完整性、符号存在或契约语义，不等于 Scope 判断和执行许可。所有检查结果均为 not_run，`execution_allowed` 在类型和 Schema 上恒为 false；W3-B 使用另一份来源重建授权，不翻转该字段。普通 SHA-1 Git profile 之外的布局/历史缺失保守 unknown，链接/损坏对象拒绝。宿主 Git、Docker daemon/WSL2、TOCTOU、容器内恶意目标干扰 pytest，以及正式 runner 供应链等剩余风险见 [安全模型](security-model.md)。

## 证据能证明什么

本地 Registry 的 enabled 仅表示可继续核验候选，不是 Active 或执行授权；每次使用仍重验原工作区来源，移动/损坏即拒绝。缺索引不自动重建，禁用为终态。Registry 身份角色、签名/防回滚、CI 权限与完整生命周期仍未覆盖，见 [Registry](registry.md)；validators 的具体阻塞见 [W3-D](progress/w3d.md)。

Evidence 要求 buggy 实际断言失败且 fixed 通过；Guard 只保留这次已失败且修复后通过的 case。验证器对引用文件校验摘要，并从原始 JUnit 重建 case 集、结果和执行分类。pytest exit 1 只有完整且准确的断言失败映射才是 violation；2/3/4/5、收集错误、缺失/矛盾 JUnit、timeout 和 launch error 不能冒充缺陷证据。

摘要用于一致性和来源关联，**不是签名或作者身份认证**。能同时改写源码、原始日志、所有关联记录及其摘要的攻击者超出了当前信任边界。验证也不能独立证明创建时间或执行主机身份真实；本机可信工具负责如实记录实际时间。已有产物的时间/ID不会为确定性重写。

单次契约通过不证明程序等价或穷尽正确；最小失败 case 筛选不等于输入 shrinking。Scope 的不可删除条件见证不证明全局最小规则或样本外泛化。当前没有自动接受变异样本、lazy/ICE learner 或自动反例标签推断。

## 实验与 unknown

scope_v1 只有公开的 15 行示例（9 train / 6 holdout）和两族 Guard。它是工程一致性与机制验证，不是盲测，也不足以外推到任意仓库。静态特征 audit 会检查全部 15 行，训练成员与正负标签只来自冻结 train；audit 出现 holdout 身份不等于 learner 使用 holdout。

标准 Demo 的六个训练目标都有完整元数据，因此没有 unknown；独立缺少声明契约的实际 Replay 展示 unknown/not_run/skipped，原因和退出 4 均保留，不加入六行 Demo 或留出分母。unknown 不等于已经确认 inapplicable，也不是通过。

所有历史来源/日志/代码 pin 不可自动刷新；代码或环境变化后的新运行使用新 ID/目录。旧 D9/D11/D12 的代码绑定应在其原提交复验，不通过重签旧 manifest 冒充当前运行。失败/部分目录不会自动恢复。

## 历史验证结论的边界

**2026-10-15 的 D13 修复提交 `14c9586` 之前（包括 `53788b1` 及更早版本），旧代码下的 verify 成功不提供本次补齐的四类攻击面的完整覆盖**：Evidence 重签失败集/来源身份、Guard 自检与原始 JUnit 矛盾、独立 Replay 执行/trace/身份重签，以及公开诊断回显私有路径或显式凭据。日期只是便于阅读的提示，同日版本以提交边界为准。

这是按入口限定的保证：旧 Gate/Evaluation/Pipeline 已有部分原始事实重建，不能据此推断旧的每个独立 verify 都具备同样保护；诊断泄漏则属于输出边界，verify 成功本身并不证明报告可公开。四类修复及具体测试见 [A01–A04](attack-surface-checklist.md)。

历史记录只证明“指定代码和输入下，当时的检查通过”。现行验证器因源码绑定拒绝旧产物，不表示已经发现它们被篡改，也不能通过切回旧代码复验就将其升级为 D13 的保证。目前没有证据表明自己生成的旧产物遭到这些攻击。需要当前保证时，在新 ID/版本目录重新物化可重跑的来源链并记录当前检查；冻结的 holdout 结论保持原版本和覆盖声明，不重跑调参或重签旧 manifest 刷新历史。

## 诊断和公开分享

CLI 自己生成的错误摘要移除显式凭据赋值和绝对路径；启动异常的结构化 error_detail 只保留异常类型。这个规则范围明确，不是通用秘密识别器；Typer 参数校验、任意应用字符串和无上下文秘密值并不由它完整覆盖。

原始 stdout/stderr/JUnit 仍保存原字节和摘要，RunRecord 的解释器 argv、case message、来源代码/契约也可能含本机路径或业务数据。JSON/Markdown 报告是对证据的忠实展示，**不是已经脱敏的公开导出包**。当前将这些本地证据视为私有；公开分享需要另行检查。不能边改写原日志“脱敏”，边继续声称原摘要可复验。

默认不把 API key 环境变量传给子 pytest，录制 AgentContext 也不包含环境、fixed 实现或 benchmark 标签。此边界不声称阻止可信目标主动读取本机文件或自行访问网络。
